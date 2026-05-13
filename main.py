"""Paper Get Agent CLI.

用法:
    python main.py path/to/paper.pdf              # 全流程分析
    python main.py path/to/paper.pdf --skip-validate  # 跳过代码验证
    python main.py path/to/paper.pdf --output reports/  # 指定输出目录
"""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import click
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from paper_get_agent.orchestrator import PaperAgent, save_report
from paper_get_agent.llm import LLMConfig

console = Console()

# ── 进度显示 ──────────────────────────────

STATUS_ICONS: dict[str, str] = {
    "start": "[cyan]●[/]",
    "step": "[yellow]◉[/]",
    "sub": "[dim]○[/]",
    "done": "[green]✔[/]",
    "skip": "[dim]─[/]",
    "error": "[red]✘[/]",
}

PHASE_LABELS: dict[str, str] = {
    "parse": "解析 PDF",
    "extract": "提取观点",
    "validate": "验证观点",
    "analyze": "局限性分析",
    "report": "生成报告",
}


class ProgressDisplay:
    """收集进度事件并渲染为 Rich Live 面板."""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self.start_time = time.time()

    def callback(self, phase: str, step: str, detail: str, elapsed: float) -> None:
        self.events.append({
            "phase": phase,
            "step": step,
            "detail": detail,
            "time": time.time() - self.start_time,
        })

    def __rich__(self) -> Panel:
        """Rich protocol: Live 每次刷新都会调用此方法."""
        lines: list[Text] = []
        elapsed = time.time() - self.start_time

        # 标题行：运行时间实时更新
        lines.append(
            Text(f"Paper Get Agent  已运行 {elapsed:.0f}s", style="bold blue")
        )
        lines.append(Text(""))

        # 未完成阶段显示 spinner 动画
        spinner_frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
        frame_idx = int(elapsed * 10) % len(spinner_frames)
        spinner = spinner_frames[frame_idx]

        # 按 phase 分组最新状态
        phase_status: dict[str, dict] = {}
        for ev in self.events:
            phase_status[ev["phase"]] = ev

        order = ["parse", "extract", "validate", "analyze", "report"]
        for phase in order:
            if phase not in phase_status:
                continue
            ev = phase_status[phase]
            icon = STATUS_ICONS.get(ev["step"], " ")
            label = PHASE_LABELS.get(phase, phase)
            detail = ev["detail"]

            # 如果当前正在执行的阶段没完成，加 spinner
            prefix = ""
            if ev["step"] in ("start", "step") and phase == self._active_phase():
                prefix = f"[yellow]{spinner}[/] "
            elif ev["step"] == "done":
                prefix = f"  {icon} "
            elif ev["step"] == "error":
                prefix = f"  {icon} "
            else:
                prefix = f"  {icon} "

            if ev["step"] == "done":
                text = Text(f"{prefix}{label}: {detail}", style="green")
            elif ev["step"] == "error":
                text = Text(f"{prefix}{label}: {detail}", style="red")
            elif ev["step"] in ("start", "step"):
                text = Text(f"{prefix}{label}: {detail}", style="yellow")
            elif ev["step"] == "sub":
                text = Text(f"     {icon} {detail}", style="dim")
            else:
                text = Text(f"{prefix}{label}: {detail}")

            lines.append(text)

            # validate 阶段展开最近子步骤
            if phase == "validate":
                subs = [
                    e for e in self.events
                    if e["phase"] == "validate" and e["step"] == "sub"
                ][-5:]
                for sub in subs:
                    dt = sub["detail"]
                    lines.append(Text(f"       {dt}", style="dim"))

        return Panel(
            Text.assemble(*[t + Text("\n") for t in lines]),
            title="Pipeline Status",
            border_style="blue",
        )

    def _active_phase(self) -> str | None:
        """返回当前正在执行（未完成）的阶段."""
        done_phases: set[str] = set()
        for ev in self.events:
            if ev["step"] == "done":
                done_phases.add(ev["phase"])
        for p in ["parse", "extract", "validate", "analyze", "report"]:
            if p in {ev["phase"] for ev in self.events} and p not in done_phases:
                return p
        return None


# ── CLI ────────────────────────────────────


@click.command()
@click.argument("paper_path", type=click.Path(exists=True))
@click.option("--output", "-o", default="output", help="输出目录")
@click.option("--skip-validate", is_flag=True, help="跳过代码验证阶段")
@click.option("--config", default="config.yaml", help="配置文件路径")
def main(paper_path: str, output: str, skip_validate: bool, config: str) -> None:
    """论文快速理解与验证 Agent."""
    console.print(f"[bold blue]Paper Get Agent v0.1.0[/]")
    console.print(f"[dim]论文: {paper_path}[/]")

    # 检查 API key
    llm_config = LLMConfig(config)
    if not llm_config.api_key:
        console.print(
            "[yellow]⚠ 未配置 API key，"
            "请设置 LLM_API_KEY 环境变量或在 config.yaml 中填写 api_key[/]"
        )

    agent = PaperAgent(skip_validation=skip_validate, config_path=config)

    # ── 实时进度面板 ──
    display = ProgressDisplay()
    live = Live(display, console=console, refresh_per_second=10)

    # 进度事件回调（由 pipeline 触发）
    def on_progress(phase: str, step: str, detail: str, elapsed: float) -> None:
        display.callback(phase, step, detail, elapsed)
        live.refresh()

    # 心跳线程：保证 LLM 阻塞等待时时间仍在走，也保证 Ctrl+C 能被处理
    stop_heartbeat = threading.Event()

    def heartbeat() -> None:
        while not stop_heartbeat.is_set():
            stop_heartbeat.wait(0.2)
            try:
                live.refresh()
            except Exception:
                break

    timer = threading.Thread(target=heartbeat, daemon=True)

    report = None
    try:
        live.start()
        timer.start()
        # 发送初始事件
        on_progress("parse", "start", "启动分析...", 0)
        report = agent.analyze(paper_path, on_progress=on_progress)
    except KeyboardInterrupt:
        console.print("\n[yellow]用户中断 (Ctrl+C)[/]")
        sys.exit(1)
    finally:
        stop_heartbeat.set()
        timer.join(timeout=1)
        live.stop()

    if report is None:
        sys.exit(1)

    # ── 保存报告 ──
    json_path = save_report(report, output_dir=output)
    md_path = Path(output) / f"{json_path.stem}.md"

    # ── 终端摘要 ──
    console.print(f"\n[bold]分析完成[/] — 评分: [bold]{report.overall_score}/10[/]")
    console.print(f"  提取方法论: {len(report.methodologies)} 个")
    console.print(f"  提取观点: {len(report.claims)} 条")
    console.print(f"  验证结果: {len(report.validations)} 条")
    console.print(f"  发现局限: {len(report.limitations)} 条")

    if report.validations:
        claim_map = {c.id: c.statement for c in report.claims}
        table = Table(title="验证摘要")
        table.add_column("Claim", style="cyan")
        table.add_column("Verdict", style="green")
        table.add_column("观点摘要", style="white")
        for v in report.validations:
            stmt = claim_map.get(v.claim_id, "?")[:60]
            table.add_row(v.claim_id, v.verdict.value, stmt)
        console.print(table)

    if report.limitations:
        console.print("\n[bold]主要局限性:[/]")
        for lim in report.limitations[:5]:
            sev_color = {
                "low": "dim",
                "medium": "yellow",
                "high": "orange1",
                "critical": "red",
            }
            color = sev_color.get(lim.severity, "white")
            console.print(
                f"  • [{color}]{lim.severity}[/] "
                f"[{lim.category.value}] {lim.description[:120]}"
            )

    console.print(f"\n[dim]报告已保存至: {json_path}[/]")
    console.print(f"[dim]Markdown: {md_path}[/]")


if __name__ == "__main__":
    main()
