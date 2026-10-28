"""Command line interface for scel2rime.

Three verbs, all offline:

    scan      look for .scel files in the places Sogou keeps user dictionaries
    info      describe one .scel file without writing anything
    convert   write .dict.yaml files for one file, many files, or a directory
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__, rime, scel

# Sogou keeps user-authored dictionaries under the roaming profile and, on some
# builds, under the install tree. Both are searched relative to the current user.
SCAN_ROOTS = (
    Path(os.environ.get("APPDATA", "")) / "SogouInput",
    Path(os.environ.get("LOCALAPPDATA", "")) / "SogouInput",
    Path(os.environ.get("USERPROFILE", "")) / "Documents" / "SogouInput",
    Path(r"C:\Program Files (x86)\Sougoupinyin\SogouInput\Data"),
    Path(r"C:\Program Files\Sougoupinyin\SogouInput\Data"),
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


def _collect(paths: list[Path]) -> list[Path]:
    """Expand files and directories into a sorted list of .scel files."""
    found: list[Path] = []
    for raw in paths:
        path = Path(raw).expanduser()
        if path.is_dir():
            found.extend(sorted(path.rglob("*.scel")))
        elif path.is_file():
            found.append(path)
        else:
            print(f"跳过不存在的路径：{path}", file=sys.stderr)
    seen: set[Path] = set()
    unique: list[Path] = []
    for item in found:
        resolved = item.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(item)
    return unique


def cmd_scan(args: argparse.Namespace) -> int:
    hits: list[Path] = []
    for root in SCAN_ROOTS:
        if not root or not Path(root).is_dir():
            continue
        print(f"搜索：{root}")
        hits.extend(sorted(Path(root).rglob("*.scel")))

    if not hits:
        print("\n没有找到 .scel 文件。")
        print("如果你是从搜狗词库官网下载的词库，直接用 convert 指定文件路径即可。")
        return 1

    print(f"\n找到 {len(hits)} 个词库：")
    for item in hits:
        size = item.stat().st_size
        print(f"  {item}  ({size:,} 字节)")
    return 0


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
        print("\n前 20 条：")
        for entry in dictionary.entries[: args.preview]:
            print(f"    {entry.word}\t{entry.pinyin}\t{entry.frequency}")
    return 0


def cmd_convert(args: argparse.Namespace) -> int:
    files = _collect(args.inputs)
    if not files:
        print("没有可转换的 .scel 文件。", file=sys.stderr)
        return 1

    if args.name and len(files) > 1:
        print("--name 只能用于单个文件。", file=sys.stderr)
        return 2

    output_dir = Path(args.output).expanduser()
    written: list[tuple[Path, str]] = []
    failures = 0

    for index, path in enumerate(files):
        try:
            dictionary = scel.parse_file(path)
        except (OSError, scel.ScelError) as error:
            print(f"跳过 {path}：{error}", file=sys.stderr)
            failures += 1
            continue

        if not dictionary.entries:
            print(f"跳过 {path}：没有解析出词条", file=sys.stderr)
            failures += 1
            continue

        name = rime.name_for(dictionary, index=index, override=args.name)
        destination = output_dir / f"{name}.dict.yaml"

        if args.stdout:
            sys.stdout.write(rime.render(dictionary, name, scale=args.scale, sort_by_weight=not args.no_sort))
            continue

        if destination.exists() and not args.force:
            print(f"已存在，跳过（用 --force 覆盖）：{destination}", file=sys.stderr)
            failures += 1
            continue

        rime.write(
            dictionary,
            destination,
            name,
            scale=args.scale,
            sort_by_weight=not args.no_sort,
            source_note=str(path),
        )
        written.append((destination, name))
        print(f"✓ {path.name} → {destination}  ({len(dictionary.entries)} 条, 名称 {name})")

        if dictionary.warnings:
            print(f"  注意：{len(dictionary.warnings)} 条警告，用 info 查看详情", file=sys.stderr)

    if not args.stdout:
        print(f"\n完成：写入 {len(written)} 个文件，失败 {failures} 个。")
        if written:
            print("\n在 schema 里启用（import_tables 用词典名，不带扩展名）：")
            print("  import_tables:")
            for _destination, name in written:
                print(f"    - {name}")
    return 0 if failures == 0 else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scel2rime",
        description="把你自己拥有的搜狗 .scel 词库转换成 Rime .dict.yaml。",
    )
    parser.add_argument("--version", action="version", version=f"scel2rime {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="查找本机的 .scel 词库")
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
    convert.set_defaults(func=cmd_convert)

    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_stdout()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
