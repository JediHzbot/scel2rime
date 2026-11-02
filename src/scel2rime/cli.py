"""Command line interface for scel2rime.

Three verbs, all offline:

    scan      look for .scel files in the places Sogou keeps user dictionaries
    info      describe one .scel file without writing anything
    convert   write .dict.yaml files for one file, many files, or a directory
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
import os
import sys
from pathlib import Path

from . import __version__, rime, scel

# Sogou keeps user-authored dictionaries under the roaming profile and, on some
# builds, under the install tree. Both are searched relative to the current user.
SCAN_ROOTS = tuple(
    Path(value) / suffix
    for variable, suffix in (
        ("APPDATA", "SogouInput"), ("LOCALAPPDATA", "SogouInput"),
        ("USERPROFILE", "Documents/SogouInput"), ("USERPROFILE", "Downloads"),
        ("ProgramFiles", "SogouInput"), ("ProgramFiles(x86)", "SogouInput"),
        ("ProgramFiles", "Sougoupinyin/SogouInput/Data"),
        ("ProgramFiles(x86)", "Sougoupinyin/SogouInput/Data"),
    ) if (value := os.environ.get(variable))
)


def _configure_stdout() -> None:
    """Keep Chinese output readable when stdout is a legacy Windows console."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


def _collect(paths: list[str | Path]) -> tuple[list[Path], list[dict]]:
    """Keep every missing/empty/unreadable input in the result ledger."""
    found: dict[Path, Path] = {}
    errors: list[dict] = []
    for raw in paths:
        path = Path(raw).expanduser()
        try:
            if path.is_dir():
                items = []
                def walk_error(error):
                    errors.append({"source": str(error.filename), "status": "failed", "reason": str(error)})
                for directory, _dirs, names in os.walk(path, onerror=walk_error):
                    items.extend(Path(directory) / name for name in names if name.lower().endswith(".scel"))
                items.sort()
                if not items:
                    errors.append({"source": str(path), "status": "failed", "reason": "目录内没有 .scel 文件"})
            elif path.is_file():
                items = [path]
            else:
                errors.append({"source": str(path), "status": "failed", "reason": "输入路径不存在"})
                continue
            for item in items:
                found.setdefault(item.resolve(), item)
        except OSError as error:
            errors.append({"source": str(path), "status": "failed", "reason": str(error)})
    return list(found.values()), errors


def cmd_scan(args: argparse.Namespace) -> int:
    roots = list(dict.fromkeys([*SCAN_ROOTS, *(Path(p).expanduser() for p in args.include)]))
    existing = [root for root in roots if root.is_dir()]
    hits, errors = _collect(existing)
    # Empty default roots are coverage information, not failed explicit inputs.
    errors = [item for item in errors if item["reason"] != "目录内没有 .scel 文件"]
    for root in args.include:
        if not Path(root).expanduser().is_dir():
            errors.append({"source": root, "status": "failed", "reason": "额外扫描目录不存在或不是目录"})
    code = 0 if hits and not errors else 1
    report = {"schema_version": 1, "operation": "scan", "roots": [str(p) for p in roots],
              "searched_roots": [str(p) for p in existing], "files": [str(p.resolve()) for p in hits],
              "errors": errors, "exit_code": code,
              "scope": "仅覆盖列出的目录；未发现不代表本机没有词库，未判断容器兼容性"}
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for root in existing:
            print(f"搜索：{root}")
        print(f"找到 {len(hits)} 个 .scel 文件（尚未验证格式）：")
        for item in hits:
            print(f"  {item}")
        for item in errors:
            print(f"{item['source']}：{item['reason']}", file=sys.stderr)
        print(report["scope"])
    return code

def cmd_info(args: argparse.Namespace) -> int:
    path = Path(args.file).expanduser()
    try:
        dictionary = scel.parse_file(path)
    except (OSError, scel.ScelError) as error:
        print(f"读取失败：{error}", file=sys.stderr)
        return 2

    print(f"文件      ：{path}")
    print(f"格式代次  ：{dictionary.format_generation}")
    print(f"词库名    ：{dictionary.name or '（空）'}")
    print(f"分类      ：{dictionary.category or '（空）'}")
    print(f"描述      ：{dictionary.description or '（空）'}")
    print(f"词条数    ：{len(dictionary.entries)}")
    print(f"音节数    ：{dictionary.syllable_count}")

    grades: dict[int, int] = {}
    for entry in dictionary.entries:
        grades[entry.frequency] = grades.get(entry.frequency, 0) + 1
    if grades:
        summary = ", ".join(f"{grade}级×{count}" for grade, count in sorted(grades.items()))
        print(f"词频分布  ：{summary}")

    if dictionary.warnings:
        print(f"警告      ：{len(dictionary.warnings)} 条")
        for warning in dictionary.warnings[:10]:
            print(f"    {warning}")
    else:
        print("警告      ：无")

    if args.preview and dictionary.entries:
        print(f"\n前 {args.preview} 条：")
        for entry in dictionary.entries[: args.preview]:
            print(f"    {entry.word}\t{entry.pinyin}\t{entry.frequency}")
    print(f"解析完整性：{'完整' if dictionary.complete else '部分恢复'}")
    return 0 if dictionary.complete else 3


def cmd_convert(args: argparse.Namespace) -> int:
    files, records = _collect(args.inputs)
    if (args.name or args.stdout) and (len(files) != 1 or records):
        print("--name / --stdout 要求一个有效文件，且没有其他无效输入。", file=sys.stderr)
        return 2
    if args.stdout and (args.json or args.dry_run):
        print("--stdout 不能与 --json / --dry-run 一起使用。", file=sys.stderr)
        return 2
    output_dir = Path(args.output).expanduser()
    planned = []
    for path in files:
        record = {"source": str(path), "status": "failed", "written": False}
        records.append(record)
        try:
            dictionary = scel.parse_file(path)
            name = rime.name_for(dictionary, override=args.name)
            destination = output_dir / f"{name}.dict.yaml"
            record.update(name=name, destination=str(destination), entries=len(rime.dedupe(dictionary.entries)),
                          parsed_entries=len(dictionary.entries), complete=dictionary.complete, warnings=dictionary.warnings)
            if not dictionary.entries:
                record["reason"] = "没有解析出词条"
                continue
            if not dictionary.complete and not args.allow_partial:
                record.update(status="partial", reason="仅部分恢复；未写入，确认后可用 --allow-partial 导出")
                continue
            planned.append((dictionary, destination, record))
        except (OSError, scel.ScelError, ValueError) as error:
            record["reason"] = str(error)

    # Compare identities case-insensitively, including on non-Windows hosts.
    counts = Counter(record["name"].casefold() for _d, _p, record in planned)
    for dictionary, destination, record in planned:
        if counts[record["name"].casefold()] > 1:
            record.update(status="conflict", reason="批内词典名冲突；请分别用 --name 重命名，--force 不会覆盖批内冲突")
            continue
        if not args.stdout and destination.exists() and not args.force:
            record.update(status="conflict", reason="输出已存在；确认后可用 --force 替换")
            continue
        try:
            if args.stdout:
                sys.stdout.write(rime.render(dictionary, record["name"], scale=args.scale, sort_by_weight=not args.no_sort))
            elif not args.dry_run:
                rime.write(dictionary, destination, record["name"], scale=args.scale,
                           sort_by_weight=not args.no_sort, source_note=str(dictionary.path))
                record["written"] = True
            record["status"] = "partial" if not dictionary.complete else ("planned" if args.dry_run else "converted")
        except (OSError, ValueError) as error:
            record.update(status="failed", reason=str(error))

    summary = dict(Counter(record["status"] for record in records))
    code = 1 if not records or any(r["status"] in {"failed", "conflict"} for r in records) else (3 if summary.get("partial") else 0)
    report = {"schema_version": 1, "operation": "convert", "dry_run": args.dry_run,
              "results": records, "summary": summary, "written_files": sum(bool(r.get("written")) for r in records), "exit_code": code}
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        stream = sys.stderr if args.stdout else sys.stdout
        for record in records:
            print(f"[{record['status']}] {record['source']}：{record.get('reason', record.get('destination', ''))}", file=stream)
            for warning in record.get("warnings", []):
                print(f"  注意：{warning}", file=stream)
        print(f"完成：写入 {report['written_files']} 个文件；状态 {summary}；退出码 {code}", file=stream)
    return code

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scel2rime",
        description="把你自己拥有的搜狗 .scel 词库转换成 Rime .dict.yaml。",
    )
    parser.add_argument("--version", action="version", version=f"scel2rime {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="查找本机的 .scel 词库")
    scan.add_argument("--include", action="append", default=[], metavar="DIR", help="额外扫描目录，可重复指定")
    scan.add_argument("--json", action="store_true", help="输出机器可读报告")
    scan.set_defaults(func=cmd_scan)

    info = subparsers.add_parser("info", help="查看一个 .scel 词库的元信息和词条")
    info.add_argument("file", help=".scel 文件路径")
    info.add_argument("--preview", type=int, default=0, metavar="N", help="额外打印前 N 条词")
    info.set_defaults(func=cmd_info)

    convert = subparsers.add_parser("convert", help="转换 .scel 文件为 Rime 词典")
    convert.add_argument("inputs", nargs="+", help=".scel 文件或包含它们的目录")
    convert.add_argument("-o", "--output", default="rime-dicts", help="输出目录（默认 rime-dicts）")
    convert.add_argument("--name", help="指定词典名（仅单文件）")
    convert.add_argument(
        "--scale",
        type=int,
        default=rime.DEFAULT_WEIGHT_SCALE,
        help=f"词频放大倍数（默认 {rime.DEFAULT_WEIGHT_SCALE}，1 表示保留原始等级）",
    )
    convert.add_argument("--no-sort", action="store_true", help="保持词库原始顺序")
    convert.add_argument("--stdout", action="store_true", help="输出到标准输出，不写文件")
    convert.add_argument("--force", action="store_true", help="覆盖已存在的输出文件")
    convert.add_argument("--allow-partial", action="store_true", help="允许导出恢复到的部分词条，仍返回退出码 3")
    convert.add_argument("--dry-run", action="store_true", help="解析和检查冲突，但不写文件")
    convert.add_argument("--json", action="store_true", help="输出逐文件 JSON 报告")
    convert.set_defaults(func=cmd_convert)

    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_stdout()
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "scale", 1) < 1:
        parser.error("--scale 必须大于 0")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
