#!/usr/bin/env bash
# 一条命令推到 GitHub 并触发 CI。需要你先装好 gh 并登录（我没有你的凭据，做不了这步）。
set -e
cd "$(dirname "$0")/.."

仓库名="${1:-filebatch}"

if ! command -v gh >/dev/null 2>&1; then
  echo "没装 gh。装法（不需要管理员密码）："
  echo "  brew install gh                      # 有 Homebrew 的话"
  echo "  或从 https://github.com/cli/cli/releases 下 macOS 包解压到 ~/.local/bin"
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "gh 还没登录，先执行：gh auth login"
  exit 1
fi

# 提交身份：没配过就用本地占位，不会外泄真实邮箱
git config user.name  >/dev/null 2>&1 || git config user.name  "dev"
git config user.email >/dev/null 2>&1 || git config user.email "dev@local"

git add -A
git diff --cached --quiet || git commit -m "推送前同步"

gh repo create "$仓库名" --private --source=. --push
echo ""
echo "已推送。看 CI 跑到哪了："
echo "  gh run watch"
echo "CI 跑完下载 Windows 包："
echo "  gh run download -n 文件批量处理工具-Windows-x64"
echo "  gh run download -n Windows-DPI截图"
