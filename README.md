# UCAS-in-windows

国科大轻新课堂 / iClass 的 Windows 精简签到程序，版本 **0.4.0**。
保留账号登录、查课表、选课签到、手动课程 ID / UUID 签到；无需 Android 环境。
学校接口已预填，普通使用只需输入自己的账号和密码。

## v0.4.0 保持登录

Windows 上默认勾选“保持登录”。第一次成功登录后，用 Windows 当前用户的 DPAPI
加密保存会话；下次启动自动读取并查询课表验证，无需再次输入账号密码。
**不保存密码**。校方会话过期后仍需重新登录，不承诺永久有效。

- 关闭窗口：保留已加密保存的会话，便于下次打开恢复。
- 退出登录：清除本机保存的会话，下次打开不会自动恢复。
- 取消“保持登录”：立即删除本机缓存，当前窗口仍保持登录，关闭后需重新登录。
- 恢复时暂时断网：显示“登录待验证”，保留缓存；网络恢复后点“查询课表”重试。
- 校方明确提示会话失效：清除缓存并提示重新登录。

加密文件位于 `%LOCALAPPDATA%\UCAS-in-windows\session.dat`，绑定当前 Windows 用户，
不适合复制到另一台电脑或另一个用户使用。Linux 源码运行不支持此 Windows 加密方式，
会禁用“保持登录”，不会回退为明文保存。删除旧版 EXE 不会删除应用数据。

## v0.3.1 界面精简

移除主界面的学校接口配置区域，地址继续使用内置值。
打开程序即可输入账号登录，登录区上移，课程列表获得更多空间。

## v0.3.0 界面更新

- 同名且同一开始/结束时间的课程合并为一行；完全相同签到编号去重。
- 若合并项包含不同的签到编号，可点左侧箭头展开查看各条记录与状态。
  选择父项时，若仍有多个待签编号，只展开列表，不会自动批量签到；请选对应子项。
  部分签完会显示“已签 1/2”，不会把整个合并项提前标成已签到。
- 日期改为可点击的日历：可选年、月、日，支持前一天、后一天和“今天”；
  已登录时选日期自动查询。日期旁的文字显示星期，列表时间简化为时分。
- 标题右侧固定显示登录状态及已登录账号，区分未登录、正在登录、登录失败和会话失效。
  查课表、无课或普通网络错误不会覆盖该状态。

## v0.2.1 修复

- 日课表改为上游使用的 GET 请求。
- 日课表状态非零或缺少数据时继续查周课表，兼容周课表的空数据响应。
- 当天无课不再一律提示“请重新登录”；仅在学校明确提示会话失效时这样提示。
- 异常课表响应显示状态码，方便进一步定位；仍需用真实有课日期验证实际课表。

## 下载

- [直接下载 Windows x64 EXE](https://github.com/OrangeArm/UCAS-in-windows/raw/refs/heads/main/releases/v0.4.0/UCAS-Sign-in.exe)
- [下载完整源码及许可证](https://github.com/OrangeArm/UCAS-in-windows/archive/refs/heads/main.zip)
- [查看文件校验值和 EXE 验证结果](releases/v0.4.0/)

EXE 已包含运行所需组件，单文件下载即可使用。若下载整个仓库，程序在
`releases/v0.4.0/UCAS-Sign-in.exe`。源码与许可证随仓库一同提供。

## 使用 EXE

适用于 **Windows 10 / 11，64 位 x64**。

1. 下载上方 EXE 并双击运行，不需要安装 Python；下载源码 ZIP 的用户请先解压。
2. 学校地址已内置，无需填写接口配置。
3. 输入学校账号与密码，点「登录」，成功后自动查询北京时间当天的课程，右上角显示“已登录 · 账号”。
4. 点击日期打开日历选择上课日期，或用左右箭头切换前后一天。选中课程，点「签到选中课程」，核对日期与课程后确认。结果以学校返回为准。
5. 课表里没有目标时，可填写 7 位课程 ID 或 32 位 UUID，再点「手动签到」。

「今天」按钮切回当天课表；勾选“保持登录”后关闭窗口即可保留登录，
只有点“退出登录”才会主动清除本机保存的会话。
网络超时后先查询课表确认结果，再决定是否重试；程序不会因超时自动重复提交。

如果学校接口需要校园网/VPN，请先连接学校提供的网络。主界面不再显示接口配置。
本程序没有后台自动签到、二维码识图、小部件或讲座发现功能。

## 账号和配置

- 密码在点击登录后清空输入框，仅供该次登录请求使用；不写入文件或日志。
- 会话在勾选“保持登录”时使用 Windows DPAPI 加密保存；未勾选时只在内存中使用。
- 学校地址已内置；兼容读取旧版 `%LOCALAPPDATA%\UCAS-in-windows\settings.json`，无需在界面配置。
- 损坏的本地配置会回退到默认值，原文件不会被自动覆盖。
- 只连接 HTTPS API，保持证书验证，不自动跟随重定向。

默认地址来自 [lccipher/UCAS-Course-Sign-in 的公开源码](https://github.com/lccipher/UCAS-Course-Sign-in/blob/c04c4ab20c740bf6c1eeb19491f87a52a9911405/src/app/api/course-uuid/query/route.ts#L199)，
不是官方承诺长期兼容的开放 API 文档：

```text
API 根地址：
https://iclass.ucas.edu.cn:8181/app/

登录校验 URL 模板：
http://iclass.ucas.edu.cn:88/ve/webservices/mobileCheck.shtml?method=mobileLogin&username=${0}&password=${1}&lx=${2}
```

模板中的 `${0}`、`${1}`、`${2}` 必须原样保留，不需要填入账号密码。
本程序仅把模板提交给学校 HTTPS API，不在本地展开模板。
不要在 URL 中填入真实凭据，也不要公开包含账号或学校配置的调试资料。

## 从源码运行

安装 Python 3.10+（推荐 3.12），保留安装程序中的 Tcl/Tk 和 Python Launcher。
解压源码包后双击 `start.bat`，也可以运行：

```bat
py -3 app.py
```

运行源码不需要 pip 依赖。

## 从源码构建 EXE

在 Windows 上运行：

```bat
build-windows.bat
```

脚本创建 `.venv-build`，安装固定版本的构建依赖，运行接口测试，
用 Windows PyInstaller 生成单文件窗口程序，然后实际运行 EXE 的离线诊断。
诊断会把 EXE 复制到含中文字符的路径，检查窗口、默认配置、模拟登录/查课/签到、
重复点击防护、加密会话保存、重建窗口自动恢复、配置保存与退出清除；不会向学校提交测试签到。

输出：

```text
dist/UCAS-Sign-in.exe
dist/build-verification.json
```

`.github/workflows/windows.yml` 提供原生 Windows 构建与测试，成功后的 artifact 包含
EXE、验证结果和说明。当前交付版本的构建/验证方式见 [VALIDATION.md](VALIDATION.md)。
Linux 原生 PyInstaller 不能生成 Windows EXE；本次使用 Wine 运行官方 Windows Python
及 Windows PyInstaller 构建，这不等同于原生 Windows 实机测试。

## 开发验证

```sh
python -m unittest discover -s tests -v
python -m unittest discover -s tests -p gui_smoke.py -v
python app.py --smoke-test smoke-result.json
```

后两个命令需要桌面显示环境。全部签到测试使用离线模拟响应，不需要真实账号。
其中 `--smoke-test` 同样适用于生成的 EXE，用于验证打包后是否缺少组件。
校方一键签到接口必须明确返回 `STATUS=0` 且 `stuSignStatus=1` 等成功判据，
程序才显示成功；仅在学校明确拒绝时间戳时重新校时并重试一次。

每个云任务已有隔离工作区，使用现有 checkout 即可，无需额外创建 Git worktree。

## 验证边界

2026-11-08 已使用无账号请求验证真实学校校时接口，返回 HTTP 200 与正常 JSON。
离线测试不能证明真实账号可登录，也不能证明某门课程可以签到。
**真实登录、课表及签到尚需使用者在自己的 Windows 上验证。**
没有代持用户账号测试，也没有尝试绕过学校签到窗口或服务端限制。

## 来源与许可证

核心流程改编自 [zhan-nine/UCAS-Sign-in](https://github.com/zhan-nine/UCAS-Sign-in)，
其参考项目为 [lccipher/UCAS-Course-Sign-in](https://github.com/lccipher/UCAS-Course-Sign-in)。
本衍生程序按 **AGPL-3.0-or-later** 分发，见 [LICENSE](LICENSE)、[NOTICE](NOTICE)。
原有 Apache-2.0 文本及所附运行库许可见 `LICENSES/`。未使用 Android LGPL 小部件代码。

分发 EXE 时请同时提供与该版本对应的完整源码及许可声明；交付 ZIP 将附带源码包。
