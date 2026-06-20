#!/usr/bin/env python3
"""
Daily English — 每日自动发布管线
由 Hermes cron 每日定时调用，完成生成→发布→归档全流程。

用法:
  python3 scripts/daily_pipeline.py                              # 生成+发布
  python3 scripts/daily_pipeline.py --dry-run                     # 生成但不发布
  python3 scripts/daily_pipeline.py --topic "会议英语"            # 指定主题
  python3 scripts/daily_pipeline.py --publish-only drafts/xxx.md  # 仅发布已有草稿

流程:
  1. 调用 DeepSeek API 生成职场英语内容
  2. 保存为 Markdown 到 drafts/
  3. 调用 publish.py 创建微信公众号草稿
  4. 归档到 published/
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_DIR / "scripts"
PYTHON = sys.executable or "python3"


def run_script(script_name: str, *args: str) -> int:
    """运行 scripts/ 下的 Python 脚本，返回退出码。"""
    script_path = SCRIPTS_DIR / script_name
    if not script_path.exists():
        print(f"❌ 脚本不存在: {script_path}")
        return 1

    cmd = [PYTHON, str(script_path), *args]
    sys.stdout.flush()
    sys.stderr.flush()
    result = subprocess.run(cmd)
    return result.returncode


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(
        description="Daily English — 每日发布管线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="仅生成内容，不实际发布")
    parser.add_argument("--topic", "-t", default="",
                        help="指定主题（传给 generate.py）")
    parser.add_argument("--publish-only", default="",
                        help="仅发布已有草稿（不生成）")
    parser.add_argument("--author", default="Daily English",
                        help="文章作者")
    parser.add_argument("--no-comment", action="store_true",
                        help="关闭评论区")

    args = parser.parse_args()

    print("=" * 50)
    print("  🌅 Daily English — 每日发布管线")
    print("=" * 50)

    # 阶段 1: 生成内容
    if args.publish_only:
        draft_path = Path(args.publish_only)
        if not draft_path.exists():
            print(f"❌ 草稿文件不存在: {draft_path}")
            sys.exit(1)
        print(f"\n📄 使用已有草稿: {draft_path}")
    else:
        print("\n📝 阶段 1/2: 内容生成")
        print("-" * 40)

        gen_args = []
        if args.topic:
            gen_args += ["--topic", args.topic]
        # Mock mode: generate sample content without API call
        gen_args += ["--mock"]

        ret = run_script("generate.py", *gen_args)
        if ret != 0:
            print("\n❌ 内容生成失败，中止管线。")
            sys.exit(ret)
        print("  ✅ 内容生成完成")

    if args.dry_run:
        print("\n🏁 Dry-run 模式，跳过发布。")
        print("   内容已在草稿目录生成（mock 内容，非真实 API 调用）")
        print("   检查生成的文件以验证排版效果。")
        return

    print("\n📰 阶段 2/2: 发布到微信公众号")
    print("-" * 40)

    pub_args = ["--author", args.author]
    if args.no_comment:
        pub_args.append("--no-comment")

    if args.publish_only:
        pub_args.append(args.publish_only)
    else:
        # 找到最新生成的草稿
        drafts = sorted(PROJECT_DIR.glob("drafts/*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not drafts:
            print("❌ 未找到草稿文件")
            sys.exit(1)
        latest = drafts[0]
        print(f"   使用最新草稿: {latest.name}")
        pub_args.append(str(latest))

    ret = run_script("publish.py", *pub_args)
    if ret != 0:
        print("\n❌ 发布失败。")
        sys.exit(ret)

    print("\n" + "=" * 50)
    print("  ✅ 每日管线执行完毕!")
    print("  ⚠️  请到公众号后台 → 草稿箱 审核后发布")
    print("=" * 50)


if __name__ == "__main__":
    main()
