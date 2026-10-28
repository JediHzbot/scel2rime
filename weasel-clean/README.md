# weasel-clean

一份给 [Weasel（小狼毫）](https://github.com/rime/weasel) 的配置包：装完就是干净的中文输入，没有皮肤商店、云端候选、浏览器组件、AI 联想。

**这是配置，不是软件。** 输入法本体是 Rime/Weasel，按 GPLv3 由上游发布；本目录只有 YAML 补丁和一个安装脚本，MIT 授权。安装脚本调用的是你已经装好的 Weasel，不下载、不打包、不修改它的任何二进制。

## 前提

先装 Weasel 并启动一次，让它生成用户目录 `%APPDATA%\Rime`。

下载：<https://github.com/rime/weasel/releases>

## 用法

```powershell
# 只装配置
.\install.ps1

# 连同 scel2rime 迁移过来的词库一起装
.\install.ps1 -From ..\rime-dicts

# 先看看会改什么
.\install.ps1 -From ..\rime-dicts -DryRun
```

脚本会做四件事：

1. 把现有配置备份到 `%APPDATA%\Rime\backup-scel2rime-<时间戳>\`
2. 写入三份 `.custom.yaml` 补丁
3. 复制 `-From` 目录里的 `.dict.yaml`，并登记词典名
4. 生成 `scel_merged.dict.yaml`，把 `luna_pinyin_simp` 和你的词库聚合到一起

然后重新部署：右键任务栏输入法图标 → 重新部署。

## 装了什么

| 文件 | 作用 |
|---|---|
| `rime/default.custom.yaml` | 候选数 9、Shift 切英文时先上屏、光标键行为、默认中文简体 |
| `rime/weasel.custom.yaml` | 一套纯色配色 `clean`、雅黑 14pt、横排、内嵌编码 |
| `rime/luna_pinyin_simp.custom.yaml` | 词典指向 `scel_merged`，关掉编码提示，保留本地用户词库 |
| `scel_merged.dict.yaml`（生成） | 聚合词典，`import_tables` 列出官方词典和你的词库 |

## 它没有装什么

- 没有皮肤商店，没有在线皮肤下载
- 没有云端候选、云同步、账号
- 没有内嵌浏览器
- 没有 AI 联想、没有模型文件
- 没有遥测

这些不是"被关掉的开关"，是 librime 本身就没有的东西。上面三份补丁里没有任何一行涉及网络。

## 回滚

```powershell
Copy-Item "$env:APPDATA\Rime\backup-scel2rime-*\*" "$env:APPDATA\Rime\" -Force
```

然后把 `scel_merged.dict.yaml` 删掉，重新部署。

## 已知限制

- 词典名默认用词库原名（通常是中文）。Rime 走 UTF-8 路径，中文名在 Windows 上正常；如果你的 librime 版本不认，用 `scel2rime convert --name ascii_name` 重转，再跑一遍本脚本。
- 配色只做了一套。想换颜色改 `weasel.custom.yaml` 里的 `preset_color_schemes`，不需要联网。
- 未在 Weasel 0.16 以下版本验证。
