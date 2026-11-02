# scel2rime

当前版本：**0.2.0**。参见 [更新记录](CHANGELOG.md)。

> 把已经导出的、兼容的词库带到 Rime，并明确报告哪些文件没有迁移。

把你有权处理的、格式兼容的搜狗词库文件（`.scel`）转成 Rime 词典（`.dict.yaml`）。转换器只使用 Python 标准库，离线运行。

本项目是**词库转换器 + 小狼毫配置包**。目前不读取搜狗个人学习数据库，不承诺迁移历史调频、账号数据或所有细胞词库；安装过某个词库，也不代表能自动找到其原始 `.scel` 文件。

```bash
scel2rime convert "C:\Users\你\Downloads\行业词库.scel" -o rime-dicts
```

```
[converted] 行业词库.scel：rime-dicts\行业词库.dict.yaml
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
| 读 `sysmodel.bin` 等系统词库 | 那是搜狗的资产，不是你的数据。另外属于另一种尚未支持的私有引擎格式 |
| 解包、修改、重打包搜狗安装程序 | 复制与发行他人软件，与"格式转换"是两件事 |
| 分发任何搜狗文件或词库内容 | 仓库只提供代码与合成测试数据，转换输出保留在本地 |
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
$env:PYTHONPATH = "src"
python -m scel2rime.cli convert 词库目录 -o rime-dicts
```

### 三个子命令

```bash
scel2rime scan
```
在常见位置和下载目录找 `.scel` 文件。报告会列出扫描范围；没有发现不等于本机不存在，也不等于发现的文件都能转换。非默认安装位置可用 `scan --include D:\词库 --json`，`--include` 可重复指定。

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
| `--force` | 替换既有输出；不会绕过同一批次的词典名冲突 |
| `--dry-run` | 解析、统计和检查冲突，不写文件 |
| `--json` | 输出逐文件状态、警告、去重后词条数及退出码 |
| `--allow-partial` | 显式导出损坏文件恢复到的词条，退出码仍为 3 |

同名冲突按不区分大小写判定，整组冲突文件都不写入。可分别使用 `--name` 重命名后再转换。`--stdout` 仅支持单个有效文件。

退出码：`0` 完整处理成功（或预演通过）；`1` 输入、冲突、读写等失败；`2` 参数错误；`3` 部分恢复，需要人工检查。混合批次有失败时返回 `1`，各文件的部分恢复状态仍保留在 JSON 中。默认不输出损坏文件的残缺词典。

```powershell
scel2rime convert .\词库目录 -o .\rime-dicts --dry-run --json
scel2rime convert .\词库目录 -o .\rime-dicts --json
```

供 agent 使用的串联方式见 [docs/automation.md](docs/automation.md)。

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

在方案里启用。别去改官方的 `luna_pinyin.dict.yaml`（它在 Program Files 里，会被升级覆盖），建一个聚合词典放进 Rime 用户目录：

```yaml
# my_dict.dict.yaml   ← name 必须和文件名一致
---
name: my_dict
version: "1"
sort: by_weight
use_preset_vocabulary: true
import_tables:
  - luna_pinyin
  - 行业词库
...
```

再让方案指向它：

```yaml
# luna_pinyin_simp.custom.yaml
patch:
  translator/dictionary: my_dict
```

然后部署。注意 `import_tables` 里写的是**词典名**（不带 `.dict.yaml`），官方自带词典只有 `luna_pinyin`、`cangjie5`、`stroke`、`terra_pinyin` 四个——`luna_pinyin_simp` 是方案名，不是词典名，写进去会报 `source file ... does not exist`。

这一步用 `weasel-clean/install.ps1` 的话是自动完成的。

## 拼音为什么能直接用

搜狗音节表里 `ü` 统一写作 `v`（`lv`、`nv`），没有声调数字，与 Rime `luna_pinyin` 的约定一致。所以转换不做任何拼音映射——映射表是错误来源，这里不需要。

## 词频为什么被放大 100 倍

`.scel` 里存的是 1–10 的**等级**，不是真实频次。原样写进 Rime，并到别的词典后区分度会被淹没。默认 ×100 让它落在手工维护词典的常见区间。想要原始值就加 `--scale 1`。

## 支持的容器

| 代次 | 状态 |
|---|---|
| 新版用户词库（头部 `0x1540`，`DCS` 魔数） | 支持已验证的结构，严格校验魔数；实际文件仍须预检 |
| 新版内置词库（头部 `0x1540`，`ECS` 魔数） | **识别并拒绝**——当前未支持此变体的词条区 |
| 旧版（头部 `0x0040`，文本拼音） | 支持词条流；头部元信息布局不稳定，词典名回退到文件名 |

格式细节见 [docs/format.md](docs/format.md)。

## 常见问题

**转出来的词条数比搜狗里显示的少？**
先看 JSON 中的 `complete`、`warnings`、`parsed_entries` 和去重后的 `entries`。重复的“词条+拼音”会合并；损坏或未知音节会标记部分恢复，默认不写出。`--allow-partial` 可导出已经恢复的部分，但不会把它报告为完整成功。恰好在词条边界截断的文件可能结构仍合法；未校验源文件声明的总词数，因此“解析完整”不等于已证明与原软件词库完全一致。

**中文词典名会不会有问题？**
Rime 走 UTF-8 路径，中文名正常。若你的某个 librime 版本不认，用 `--name pinyin_name` 换成 ASCII。

**能不能转搜狗的系统词库？**
当前不支持系统引擎数据库和 ECS 变体。文件魔数只用于格式识别，不能用于判断内容归属或授权。

**会不会把我自己的词库上传？**
不会。代码里没有网络模块，`pip install` 之后断网也能用。

## 配套：weasel-clean 配置包

转完词库，还差一个能用的输入法。`weasel-clean/` 是一份给 Weasel（小狼毫）的配置包：

```powershell
cd weasel-clean
.\install.ps1 -From ..\rime-dicts -Deploy
```

它先检查全部输入，再备份所有将被覆盖的配置和词典，保存带 SHA-256 的恢复清单。加 `-Deploy` 时还备份编译目录及部署元数据；部署在独立进程中执行，有超时、原生日志检查和新产物验证。失败会自动恢复，成功后也可按本次备份精确回滚。不会将旧的 `.table.bin` 当作本次成功。

装完是：候选数 9、Shift 切英文先上屏、纯色配色、横排内嵌编码、本地用户词库。没有皮肤商店、云端候选、内嵌浏览器、AI 联想——这些不是被关掉的开关，是 librime 本来就没有的东西。

配置是 MIT，输入法本体是上游的 GPLv3 Weasel，脚本只调用你已装好的那一个。见 [weasel-clean/README.md](weasel-clean/README.md)。

## 开发

```bash
python -m unittest discover -s tests -v
```

测试覆盖解析、渲染、批处理状态、原子写入以及 Windows 安装/部署恢复。PowerShell 集成测试使用临时目录与模拟 worker，不调用真实输入法服务；非 Windows 环境会跳过这些测试。真实引擎编译验证与界面打字验收是另外两层，见 [docs/validation.md](docs/validation.md)。仓库不包含第三方词库。

## 许可证

MIT。见 [LICENSE](LICENSE)。
