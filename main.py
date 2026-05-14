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
    "start": "[cyan]○[/]",
    "step": "[yellow]◉[/]",
    "sub": "[dim]  [/]",
    "done": "[green]✔[/]",
    "skip": "[dim]─[/]",
    "error": "[red]✘[/]",
}

PHASE_LABELS: dict[str, str] = {
    "parse": "1/5 解析 PDF",
    "extract": "2/5 提取方法论与观点",
    "validate": "3/5 验证观点",
    "analyze": "4/5 局限性分析",
    "summarize": "5/5 生成总结",
    "report": "导出报告",
}

SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


class ProgressDisplay:
    """收集进度事件并渲染为 Rich Live 面板.

    三层粒度:
    - phase: 大阶段 (parse/extract/validate/analyze/report)
    - step: 阶段内步骤 (会随阶段推进更新)
    - sub: 步骤内子步骤 (展示在对应阶段下方)
    """

    def __init__(self) -> None:
        self.events: list[dict] = []
        self.start_time = time.time()
        self._phase_starts: dict[str, float] = {}   # 每阶段何时开始

    def callback(self, phase: str, step: str, detail: str, elapsed: float) -> None:
        now = time.time() - self.start_time
        if step == "start":
            self._phase_starts[phase] = now
        self.events.append({
            "phase": phase,
            "step": step,
            "detail": detail,
            "time": now,
        })

    def __rich__(self) -> Panel:
        lines: list[Text] = []
        now = time.time() - self.start_time

        # ── 头部: 总运行时间 ──
        mins, secs = divmod(int(now), 60)
        ts = f"{mins}m {secs:02d}s" if mins else f"{secs}s"
        lines.append(Text(f"Paper Get Agent  已运行 {ts}", style="bold blue"))

        # ── 进度条 ──
        phase_order = ["parse", "extract", "validate", "analyze", "summarize"]
        done_count = sum(1 for p in phase_order if self._phase_done(p))
        bar_width = 30
        filled = int(bar_width * done_count / len(phase_order))
        active_phase = self._active_phase()
        if active_phase and active_phase in phase_order:
            # 当前阶段的部分进度用不同字符
            bar = "█" * filled + "▓" + "░" * (bar_width - filled - 1)
        else:
            bar = "█" * filled + "░" * (bar_width - filled)
        lines.append(Text(f"  [{done_count}/{len(phase_order)}] {bar}", style="bold"))

        lines.append(Text(""))

        # ── 各阶段状态 ──
        frame_idx = int(now * 10) % len(SPINNER_FRAMES)
        spinner = SPINNER_FRAMES[frame_idx]

        phase_status: dict[str, dict] = {}
        for ev in self.events:
            phase_status[ev["phase"]] = ev

        for phase in ["parse", "extract", "validate", "analyze", "summarize", "report"]:
            if phase not in phase_status:
                continue
            ev = phase_status[phase]
            icon = STATUS_ICONS.get(ev["step"], " ")
            label = PHASE_LABELS.get(phase, phase)
            detail = ev["detail"]

            # 每阶段已用时间
            phase_elapsed = ""
            if phase in self._phase_starts and not self._phase_done(phase):
                pe = now - self._phase_starts[phase]
                if pe > 1:
                    pm, ps = divmod(int(pe), 60)
                    phase_elapsed = f" [{pm}m {ps:02d}s]" if pm else f" [{ps}s]"

            # 前缀
            if ev["step"] in ("start", "step") and phase == active_phase:
                prefix = f"[yellow]{spinner}[/] " if phase != "report" else "  "
            elif ev["step"] == "done":
                prefix = f"  {icon} "
            elif ev["step"] == "error":
                prefix = f"  {icon} "
            elif ev["step"] == "skip":
                prefix = f"  {icon} "
            else:
                prefix = f"  {icon} "

            if ev["step"] == "done":
                color = "green"
            elif ev["step"] == "error":
                color = "red"
            elif ev["step"] in ("start", "step") and phase == active_phase:
                color = "yellow"
            elif ev["step"] == "skip":
                color = "dim"
            else:
                color = "white"

            text = Text(f"{prefix}{label}: {detail}{phase_elapsed}", style=color)
            lines.append(text)

            # ── 展开子步骤 (不限于 validate) ──
            subs = [
                e for e in self.events
                if e["phase"] == phase and e["step"] == "sub"
            ][-6:]
            for sub in subs:
                st = sub["time"]
                lines.append(Text(f"       {icon} {sub['detail']}", style="dim"))

        return Panel(
            Text.assemble(*[t + Text("\n") for t in lines]),
            title="Pipeline Status",
            border_style="blue",
        )

    def _phase_done(self, phase: str) -> bool:
        for ev in self.events:
            if ev["phase"] == phase and ev["step"] == "done":
                return True
        return False

    def _active_phase(self) -> str | None:
        for p in ["parse", "extract", "validate", "analyze", "summarize", "report"]:
            has_events = any(e["phase"] == p for e in self.events)
            is_done = self._phase_done(p)
            if has_events and not is_done:
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

    # ── Per-claim 摘要 ──
    if report.claims and any(c.summary for c in report.claims):
        console.print("\n[bold]核心主张摘要:[/]")
        for c in report.claims:
            if c.summary:
                console.print(f"  • [cyan]{c.id}[/] {c.summary}")

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
        from paper_get_agent.models.paper import LIMITATION_CATEGORY_ZH, SEVERITY_ZH
        console.print("\n[bold]主要局限性:[/]")
        for lim in report.limitations[:5]:
            sev_color = {
                "low": "dim",
                "medium": "yellow",
                "high": "orange1",
                "critical": "red",
            }
            color = sev_color.get(lim.severity, "white")
            sev_zh = SEVERITY_ZH.get(lim.severity, lim.severity)
            cat_zh = LIMITATION_CATEGORY_ZH.get(lim.category.value, lim.category.value)
            console.print(
                f"  • [{color}]{sev_zh}[/] "
                f"[{cat_zh}] {lim.description[:120]}"
            )

    console.print(f"\n[dim]报告已保存至: {json_path}[/]")
    console.print(f"[dim]Markdown: {md_path}[/]")


if __name__ == "__main__":
    main()
