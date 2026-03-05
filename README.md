# Pokefetch

一个用于辅助制作 Pokemon 相关 PPT 的小工具：
- 从 [wiki.52poke.com](https://wiki.52poke.com/) 抓取指定宝可梦信息
- 生成本地 HTML 页面，便于复制内容到 PPT

## 功能概览

- 支持按 **全国图鉴编号** 或 **中文名** 查询（如 `0001`、`妙蛙种子`）
- 抓取并展示：
  - 属性与属性克制（含多形态）
  - 种族值表
  - 技能列表（升级 / 学习器）
  - 形态技能池汇总（本系/非本系、物理/特殊/变化）
- 自动下载宝可梦图片到本地
- 生成本地网页（包含样式与属性图标资源）
- 支持页面缓存（加快重复抓取）

## 环境要求

- Python 3.13（见 `.python-version`）
- [uv](https://docs.astral.sh/uv/) 包管理工具

## 安装依赖

```bash
uv sync
```

## 构建 EXE（Windows）

项目使用统一发布脚本：`release_exe.bat`

```bat
release_exe.bat [spec_file] [exe_name]
```

参数说明：
- `spec_file`（可选）：用于控制打包行为的 `.spec` 文件，默认 `pokefetch.spec`
- `exe_name`（可选）：期望生成的 EXE 名称（不含 `.exe`），默认 `pokefetch`

该脚本会自动：
- 清理旧产物（`build/`、`dist/`）
- 保留并使用传入的 `.spec` 文件（不再删除）
- 检查/安装 PyInstaller（若缺失）
- 根据 `.spec` 构建 EXE
- 同步可编辑配置到 `dist/config/`
- 生成发布压缩包

`dist/` 中可编辑配置文件位置：

- `dist/config/name_mapping.txt`
- `dist/config/ignore_skills.txt`

默认会生成发布压缩包：

- `dist/pokefetch.zip`

压缩包内包含：

- `pokefetch.exe`
- `config/name_mapping.txt`
- `config/ignore_skills.txt`

打包示例：

```bat
release_exe.bat
release_exe.bat pokefetch.spec pokefetch
```

运行 EXE 示例：

```bat
pokefetch.exe 0003
pokefetch.exe 妙蛙花 --output-dir out
```

> 说明：EXE 可独立运行（无需本机 Python 环境），但抓取数据时仍需要网络连接。

## 使用方法

### 基本命令

```bash
uv run python main.py [identifier]
```

- 默认会启动本地服务（左侧搜索列表 + 右侧详情页）
- 左侧支持中文、拼音、英文搜索，显示编号/中文名/英文名/属性
- 提供“手气不错”随机按钮与“刷新列表（重新拉取）”按钮
- 运行服务时，在命令行按 `Enter` 可重新打开页面，按 `Ctrl+C` 停止服务
- `identifier` 可选；提供后会在页面打开后优先加载该宝可梦
- `identifier` 可以是：
  - 图鉴编号（如 `0003`）
  - 宝可梦名称（如 `妙蛙花`）

### 常用示例

```bash
# 启动本地服务（默认模式）
uv run python main.py

# 启动本地服务，并默认打开该宝可梦详情
uv run python main.py 0003

# 可用英文/拼音搜索（在左侧搜索框输入）
# 例如: bulbasaur / pika / pkq

# 指定输出目录
uv run python main.py --output-dir demo_out

# 仅执行抓取并生成（旧逻辑）
uv run python main.py 0006 -f

# 仅抓取模式下：禁用缓存
uv run python main.py 0006 -f --no-cache

# 仅抓取模式下：刷新缓存
uv run python main.py 0006 -f --refresh-cache

# 仅抓取模式下：生成后自动打开网页
uv run python main.py 0006 -f -w
```

## 命令行参数

| 参数 | 说明 | 默认值 |
|---|---|---|
| `identifier` | 宝可梦编号或名称（可选；`-f` 模式下必填） | - |
| `--output-dir` | 输出目录 | `out` |
| `--no-cache` | 禁用页面缓存，每次都重新请求 | `false` |
| `--refresh-cache` | 刷新缓存（重新请求并覆盖缓存） | `false` |
| `-w`, `--open-web` | 生成后自动用系统默认浏览器打开网页（`-f` 模式） | `false` |
| `-f`, `--fetch-only` | 仅执行抓取并生成（旧逻辑），不启动本地服务 | `false` |

## 输出规则

- 输出目录默认是：`out/`
- 生成网页文件名格式：`ID名称.html`
  - 例如：`0003妙蛙花.html`
- 下载图片文件名格式：`ID名称.png`
  - 例如：`0003妙蛙花.png`

示例（执行 `uv run python main.py 0003`）：

```text
out/
├── 0003妙蛙花.html
├── 0003妙蛙花.png
├── wiki_site_styles.css
└── icons/
```

## 可选配置文件

- `config/name_mapping.txt`：名称映射（例如属性全称/简称映射）
- `config/ignore_skills.txt`：在“形态技能池汇总”中过滤的技能名（每行一个，可用 `#` 注释）

## 缓存说明

- 页面缓存目录：`.cache/pages/`
- 默认启用缓存；可通过 `--no-cache` 关闭
- 需要更新已缓存页面时可使用 `--refresh-cache`

## 注意事项

- 本工具依赖目标站点页面结构，若站点改版可能需要调整解析逻辑
- 首次抓取或未命中缓存时会进行网络请求

## 鸣谢

- 数据源：https://wiki.52poke.com/
- icon 源：https://tw.portal-pokemon.com/game/type-chart/
