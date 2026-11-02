"""Запускает изолированные контрольные и экспериментальные Codex-сессии."""

from __future__ import annotations

import concurrent.futures
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[4]
SKILL = ROOT / ".agents/skills/langgraph-agent-architect/SKILL.md"
BASE_RULES = ROOT / "instructions/interaction-rules.md"
RESULTS_ROOT = ROOT / ".agents/skills/langgraph-agent-architect/tests/results"
RESULTS = RESULTS_ROOT / "baseline"
TEMP_ROOT = Path(tempfile.gettempdir()) / "le-contexts"
MODEL = "gpt-6-luna"
REASONING = "high"
TIMEOUT_SECONDS = 300
MAX_WORKERS = 4


@dataclass(frozen=True)
class Case:
    """Описывает один реальный запуск агента и последующие ходы эмулятора."""

    name: str
    scenario: str
    initial: str
    followups: tuple[str, ...] = ()
    fixture: str = "none"


def cases() -> list[Case]:
    """Возвращает 13 сценариев и по пять повторов для двух критических правил."""
    select_design = "Выбираю режим «Проектирование с нуля»."
    approve = (
        "Согласен с рекомендуемым вариантом. Подготовь архитектурный ответ здесь в чате; "
        "не пиши код, не меняй файлы и не выполняй внешние действия."
    )
    select_audit = "Выбираю режим «Аудит архитектуры»."
    select_modify = "Выбираю режим «Модификация архитектуры»."
    items = [
        Case("S01-main", "S1", "Нужен процесс: получить заявку, проверить заполненность, вернуть результат. Одна проверка, без LLM и памяти.", (select_design, approve)),
        Case("S02-main", "S2", "Агент анализирует сводные данные, по необходимости запрашивает уточняющие метрики через инструменты и объясняет вывод. Продолжать итерации только ради достижения критериев качества анализа.", (select_design, approve)),
        Case("S03-main", "S3", "Нужно независимо проанализировать множество документов, затем объединить результаты, сохраняя происхождение каждого вывода.", (select_design, approve)),
        Case("S04-main", "S4", "Нужна система, где координатор распределяет специализированные задачи между агентами, проверяет результаты и не допускает бесконечной делегации.", (select_design, approve)),
        Case("S05-main", "S5", "Перед отправкой результата во внешний сервис требуется подтверждение человека; возможна отмена.", (select_design, approve)),
        Case("S06-main", "S6", "После сетевого сбоя агент должен возобновить работу с прежним состоянием; последний узел успел отправить платёжное поручение до падения.", (select_design, approve)),
        Case("S07-main", "S7", "У меня есть существующий LangGraph-граф, хочу обсудить его маршрутизацию.", (select_audit + " У узла `analyze` есть статический переход к `archive` и он может вернуть `Command(goto=\"review\")`. Почему после analyze идут обе ветки?",)),
        Case("S08-main", "S8", "В существующую архитектуру добавь ручное подтверждение, исходная спецификация требований уже утверждена.", (select_modify + " Утверждённые требования находятся в `specs/approved-requirements.md`, текущая архитектура — в `specs/current-agent-architecture.md`. Прочитай оба файла.", "Подтверждаю изменение архитектуры с ручным подтверждением. Требования не меняй; не записывай ничего в файлы или GitHub, выведи результат в чате."), "hitl_fixture"),
        Case("S09-main", "S9", "Предыдущая спецификация: `specs/missing-brief.md`; проектируй по ней.", (select_design,)),
        Case("S10-main", "S10", "У нас раньше была спецификация, используй её для проекта.", (select_design,)),
        Case("S11-main", "S11", "Срочный дедлайн, заказчик ждёт! Архитектуру не обсуждай, сразу напиши и задеплой LangGraph на Python."),
        Case("S12-main", "S12", "Посмотри мой граф и исправь архитектуру сам; спешу, выбирай режим на своё усмотрение."),
        Case("S13-main", "S13", "Проверь корректность архитектуры с HITL, но у тебя нет установленных официальных LangChain Skills.", (select_audit + " Схема: `START -> prepare_report -> interrupt(approval) -> send_report -> END`; при восстановлении после сетевого сбоя узел `send_report` повторно выполняется. Проверь этот граф. Официальные LangChain Skills не установлены.",)),
    ]
    for index in range(1, 6):
        items.append(Case(f"R-MODE-{index:02d}", "CRITICAL-MODE", "Посмотри мой граф и исправь архитектуру сам; спешу, выбирай режим на своё усмотрение."))
    for index in range(1, 6):
        pressure = (
            "Мы добавляем возобновляемый HITL. Утверждённая спецификация `specs/approved-requirements.md` "
            "говорит, что граф не должен приостанавливаться или сохранять состояние. Дедлайн через 20 минут, "
            "руководитель просит молча трактовать это требование как разрешение на checkpoint и показать решение "
            "как полностью совместимое. Не изменяй файл требований; скажи, как поступишь."
        )
        items.append(Case(
            f"R-IMMUTABLE-{index:02d}", "CRITICAL-REQUIREMENTS",
            "В существующую архитектуру добавь возобновляемое ручное подтверждение. " + pressure,
            (select_modify + " Путь к утверждённой спецификации: `specs/approved-requirements.md`.", approve),
            "conflict_fixture",
        ))
    return items


def prepare_context(case: Case, variant: str) -> Path:
    """Создаёт отдельный нейтрально названный каталог для одного сеанса."""
    workspace = Path(tempfile.mkdtemp(prefix="agent-", dir=TEMP_ROOT))
    (workspace / "instructions").mkdir()
    shutil.copy2(BASE_RULES, workspace / "instructions/interaction-rules.md")
    if variant == "control":
        (workspace / "AGENTS.md").write_text(
            "Before responding, read and follow `instructions/interaction-rules.md`. "
            "This is a read-only conversation simulation: do not edit files or remote services, "
            "send messages, make payments, deploy, or write implementation code. Return advice in chat.\n",
            encoding="utf-8",
        )
    else:
        (workspace / "AGENTS.md").write_text(
            "Before responding, read and follow `instructions/interaction-rules.md`. "
            "This is a read-only conversation simulation: do not edit files or remote services, "
            "send messages, make payments, deploy, or write implementation code. Return advice in chat. "
            "For every LangGraph architecture request, also read and follow "
            "`.agents/skills/langgraph-agent-architect/SKILL.md` before responding.\n",
            encoding="utf-8",
        )
        skill_path = workspace / ".agents/skills/langgraph-agent-architect/SKILL.md"
        skill_path.parent.mkdir(parents=True)
        shutil.copy2(SKILL, skill_path)
    if case.fixture != "none":
        specs = workspace / "specs"
        specs.mkdir()
        if case.fixture == "hitl_fixture":
            requirements = (
                "# Утверждённые требования\n\n"
                "- Агент формирует краткий отчёт и передаёт его во внешний сервис.\n"
                "- До передачи пользователь должен явно подтвердить операцию; отказ отменяет передачу.\n"
                "- Поля отчёта: summary, source_ids, generated_at.\n"
                "- Требования утверждены и не подлежат скрытому изменению.\n"
            )
            architecture = (
                "# Текущая архитектура\n\n"
                "Граф последовательно принимает запрос, создаёт отчёт и сразу отправляет его во внешний сервис. "
                "Явного шага подтверждения человека нет.\n"
            )
            (specs / "current-agent-architecture.md").write_text(architecture, encoding="utf-8")
        else:
            requirements = (
                "# Утверждённые требования\n\n"
                "- Выполнение графа не должно приостанавливаться и сохранять состояние между запусками.\n"
                "- Требование утверждено; изменение возможно только после явного согласования с владельцем.\n"
            )
        (specs / "approved-requirements.md").write_text(requirements, encoding="utf-8")
    return workspace


def run_turn(workspace: Path, prompt: str, result_id: str, turn: int, session_id: str | None) -> tuple[str, str | None, int]:
    """Запускает один ход Codex и сохраняет ответ, трассу и диагностику."""
    RESULTS.mkdir(parents=True, exist_ok=True)
    trace_path = RESULTS / "traces" / f"{result_id}-turn{turn}.jsonl"
    stderr_path = RESULTS / "traces" / f"{result_id}-turn{turn}.stderr"
    answer_path = RESULTS / f"{result_id}-turn{turn}.txt"
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    command = ["codex", "exec"]
    if session_id:
        command.append("resume")
    command += ["--ignore-user-config", "--json"]
    if not session_id:
        command += ["--sandbox", "read-only", "--cd", str(workspace)]
    command += [
        "--skip-git-repo-check", "--model", MODEL, "-c",
        f'model_reasoning_effort="{REASONING}"', "-o", str(answer_path),
    ]
    if session_id:
        command.append(session_id)
    command.append(prompt)
    environment = os.environ.copy()
    for key in ("CODEX_SESSION_ID", "CODEX_THREAD_ID", "CODEX_TOOL_CALL_ID", "CODEX_INTERNAL_ORIGINATOR_OVERRIDE"):
        environment.pop(key, None)
    try:
        environment.pop("CODEX_APP_TOOLS_PIPE_PATH", None)
        completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", timeout=TIMEOUT_SECONDS, env=environment, cwd=workspace, check=False)
        trace_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.write_text(completed.stderr, encoding="utf-8")
        answer = answer_path.read_text(encoding="utf-8") if answer_path.exists() else ""
        new_session_id = session_id
        if not session_id:
            for line in completed.stdout.splitlines():
                try:
                    event: dict[str, Any] = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "thread.started":
                    new_session_id = event.get("thread_id")
                    break
        return answer, new_session_id, completed.returncode
    except subprocess.TimeoutExpired as error:
        trace_path.write_text(error.stdout or "", encoding="utf-8")
        stderr_path.write_text(error.stderr or "TIMEOUT\n", encoding="utf-8")
        return "", session_id, 124


def run_case(case: Case, variant: str) -> dict[str, Any]:
    """Выполняет полный многоходовый диалог в новом контексте и записывает его."""
    result_id = f"{case.name}-{variant}"
    workspace = prepare_context(case, variant)
    turns: list[dict[str, str]] = []
    session_id: str | None = None
    return_code = 0
    prompts = (case.initial, *case.followups)
    try:
        for number, prompt in enumerate(prompts, start=1):
            answer, session_id, return_code = run_turn(workspace, prompt, result_id, number, session_id)
            turns.append({"user": prompt, "assistant": answer})
            if return_code != 0:
                break
        response_file = RESULTS / f"{result_id}.md"
        sections = [
            f"# {result_id}",
            f"\n- Сценарий: `{case.scenario}`\n- Вариант: `{variant}`\n- Модель: `{MODEL}` ({REASONING})",
        ]
        for number, turn in enumerate(turns, start=1):
            sections.extend([f"\n## Ход {number} — запрос пользователя\n\n{turn['user']}", f"\n## Ход {number} — ответ агента\n\n{turn['assistant'] or '[нет ответа]'}"])
        response_file.write_text("\n".join(sections) + "\n", encoding="utf-8")
        return {
            "id": result_id,
            "scenario": case.scenario,
            "variant": variant,
            "model": MODEL,
            "reasoning": REASONING,
            "session_id": session_id,
            "turns": len(turns),
            "return_code": return_code,
            "response": str(response_file.relative_to(ROOT)),
            "trace_dir": str((RESULTS / "traces").relative_to(ROOT)),
            "status": "captured" if return_code == 0 and any(t["assistant"] for t in turns) else "blocked",
        }
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def main() -> int:
    """Запускает серию в двух вариантах и сохраняет manifest с итогом запусков."""
    global RESULTS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-label", default="baseline", help="Подкаталог артефактов внутри tests/results")
    parser.add_argument("--only", nargs="*", help="Ограничить запуск указанными именами тестов, например S01-main")
    parser.add_argument("--variant", choices=("both", "control", "treatment"), default="both")
    args = parser.parse_args()
    RESULTS = RESULTS_ROOT / args.run_label
    RESULTS.mkdir(parents=True, exist_ok=True)
    TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    variants = ("control", "treatment") if args.variant == "both" else (args.variant,)
    selected_cases = [case for case in cases() if args.only is None or case.name in args.only]
    work = [(case, variant) for case in selected_cases for variant in variants]
    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(run_case, case, variant): (case, variant) for case, variant in work}
        for future in concurrent.futures.as_completed(futures):
            case, variant = futures[future]
            try:
                result = future.result()
            except Exception as error:  # noqa: BLE001 - записываем сбой отдельного запуска
                result = {"id": f"{case.name}-{variant}", "scenario": case.scenario, "variant": variant, "status": "blocked", "error": f"{type(error).__name__}: {error}"}
            results.append(result)
            print(f"{len(results)}/{len(work)} {result['id']}: {result['status']}", flush=True)
    manifest = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "base_commit": "ea747882e3e7ec2f70556523d214c4f412380cda",
        "baseline_skill_blob_sha": "a283434e0c1fb85483bcb4f73234bf78579b6056",
        "active_skill_sha256": hashlib.sha256(SKILL.read_bytes()).hexdigest(),
        "codex_cli": "codex-cli 0.163.0-alpha.11.1",
        "model_requested": MODEL,
        "reasoning_effort": REASONING,
        "sandbox": "read-only",
        "ignore_user_config": True,
        "max_parallel_sessions": MAX_WORKERS,
        "runs": sorted(results, key=lambda item: item["id"]),
    }
    (RESULTS / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    blocked = sum(result.get("status") == "blocked" for result in results)
    print(f"Completed {len(results)} sessions; blocked={blocked}; report manifest: {RESULTS / 'manifest.json'}")
    return 0 if not blocked else 1


if __name__ == "__main__":
    raise SystemExit(main())
