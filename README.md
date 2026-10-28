# scel2rime

> 换输入法最贵的成本不是重背键位，是十年的词库带不走。

把**你自己做的**搜狗词库（`.scel`）转成 Rime 词典（`.dict.yaml`）。一条命令，零依赖，纯离线。

```bash
scel2rime convert "C:\Users\你\Downloads\行业词库.scel" -o rime-dicts
```

```
✓ 行业词库.scel → rime-dicts\行业词库.dict.yaml  (12034 条, 名称 行业词库)
```

## 它做什么

- 读 `.scel` 容器，还原词条、拼音、词频等级
- 输出标准 Rime 词典，`import_tables` 直接可用
- 批量转换整个目录
- 只依赖 Python 标准库，Windows / macOS / Linux 都能跑
- 全程离线，没有网络请求，没有遥测

## 它不做什么

这几条是硬边界，不是免责声明：

| 不做 | 原因 |
|---|---|
| 读 `sysmodel.bin` 等系统词库 | 那是搜狗的资产，不是你的数据。另外它 320 MB，是私有引擎格式 |
| 解包、修改、重打包搜狗安装程序 | 复制与发行他人软件，与"格式转换"是两件事 |
| 分发任何搜狗文件或词库内容 | 仓库里只有代码和你自己转出来的文件 |
| 联网 | 转换是纯本地字节操作，不需要网络 |

换句话说：**工具处理的是你手上的数据，不是厂商的产品。**

## 快速开始

需要 Python 3.10+。

```bash
git clone https://github.com/JediHzbot/scel2rime
cd scel2rime
pip install -e .
```

不想装也行，直接跑模块：

```bash
set PYTHONPATH=src
python -m scel2rime.cli convert 词库目录 -o rime-dicts
```

### 三个子命令

```bash
scel2rime scan
```
在常见位置找 `.scel` 文件（`%APPDATA%\SogouInput`、安装目录的 `Data` 等）。

```bash
scel2rime info 词库.scel --preview 10
```
不写任何文件，只看元信息和前几条词——转换前先确认解析正确。

```bash
scel2rime convert 词库.scel 词库目录 -o rime-dicts
```
写 `.dict.yaml`。参数：

| 参数 | 作用 |
|---|---|
| `-o, --output` | 输出目录，默认 `rime-dicts` |
| `--name` | 指定词典名（仅单文件） |
| `--scale` | 词频放大倍数，默认 100；`1` 保留原始 1–10 等级 |
| `--no-sort` | 保持词库原始顺序 |
| `--stdout` | 打到标准输出，不落盘 |
| `--force` | 覆盖已存在的输出 |

## 生成的词典长什么样

```yaml
# Rime dictionary
# encoding: utf-8
# source: C:\Users\你\Downloads\行业词库.scel
# entries: 12034

---
name: 行业词库
version: "1"
sort: by_weight
use_preset_vocabulary: true
columns:
  - text
  - code
  - weight
...

信息系统	xin xi xi tong	1000
公务网	gong wu wang	900
上行链路	shang xing lian lu	800
```

在输入方案里启用，编辑 `luna_pinyin.custom.yaml`：

```yaml
patch:
  "translator/dictionary": luna_pinyin
```

再在 `luna_pinyin.dict.yaml` 的 `import_tables` 里加一行词典名（不带扩展名）：

```yaml
import_tables:
  - luna_pinyin
  - 行业词库
```

重新部署，词库就进来了。

## 拼音为什么能直接用

搜狗音节表里 `ü` 统一写作 `v`（`lv`、`nv`），没有声调数字，与 Rime `luna_pinyin` 的约定一致。所以转换不做任何拼音映射——映射表是错误来源，这里不需要。

## 词频为什么被放大 100 倍

`.scel` 里存的是 1–10 的**等级**，不是真实频次。原样写进 Rime，并到别的词典后区分度会被淹没。默认 ×100 让它落在手工维护词典的常见区间。想要原始值就加 `--scale 1`。

## 支持的容器

| 代次 | 状态 |
|---|---|
| 新版用户词库（头部 `0x1540`，`DCS` 魔数） | 完整支持，实测样本 0 警告 |
| 新版内置词库（头部 `0x1540`，`ECS` 魔数） | **识别并拒绝**——随输入法安装的词库，不是你的数据 |
| 旧版（头部 `0x0040`，文本拼音） | 支持词条流；头部元信息布局不稳定，词典名回退到文件名 |

格式细节见 [docs/format.md](docs/format.md)。

## 常见问题

**转出来的词条数比搜狗里显示的少？**
`info` 里的警告会说明停在哪。截断的文件能救回前面全部内容，损坏的字段值会让解析在那一处停下，而不是整份放弃。

**中文词典名会不会有问题？**
Rime 走 UTF-8 路径，中文名正常。若你的某个 librime 版本不认，用 `--name pinyin_name` 换成 ASCII。

**能不能转搜狗的系统词库？**
不转，理由见上面的边界表。系统词库是引擎的一部分，转换它既越界也没有实际收益——它的内容本来就来自公开语料，Rime 社区的开源词库覆盖得更好。

**会不会把我自己的词库上传？**
不会。代码里没有网络模块，`pip install` 之后断网也能用。

## 配套：weasel-clean 配置包

转完词库，还差一个能用的输入法。`weasel-clean/` 是一份给 Weasel（小狼毫）的配置包：

```powershell
cd weasel-clean
.\install.ps1 -From ..\rime-dicts
```

它会备份现有配置、写入三份 YAML 补丁、把迁移过来的词库聚合进 `luna_pinyin_simp`，然后等你重新部署。

装完是：候选数 9、Shift 切英文先上屏、纯色配色、横排内嵌编码、本地用户词库。没有皮肤商店、云端候选、内嵌浏览器、AI 联想——这些不是被关掉的开关，是 librime 本来就没有的东西。

配置是 MIT，输入法本体是上游的 GPLv3 Weasel，脚本只调用你已装好的那一个。见 [weasel-clean/README.md](weasel-clean/README.md)。

## 开发

```bash
python -m unittest discover -s tests -v
```

17 个测试，全部基于 `tests/builders.py` 现场构造的合成容器，仓库里不含任何第三方词库。

## 许可证

MIT。见 [LICENSE](LICENSE)。
