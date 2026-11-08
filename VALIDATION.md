# v0.2.0 验证记录

日期：2026-11-08（北京时间）。

## 构建

- 执行主机：Debian 13 x86-64。
- Windows 运行环境：Wine 10.0（Debian 软件包，APT 使用签名验证及包校验）。
- Windows Python：从 python.org 通过验证 TLS 的 HTTPS 下载 CPython 3.12.10 amd64
  官方 MSI，包含核心、标准库、解释器、Tcl/Tk、pip 与开发组件。
- Windows PyInstaller：6.16.0。依赖版本见 `requirements-build.txt`。
- 输出为真正的 **PE32+ x86-64 Windows GUI EXE**，不是 Linux 可执行文件改名。
- 使用标准 PyInstaller 单文件窗口模式构建；对应原生 Windows 命令见 `build-windows.bat`。

## 已通过

- Linux Python 3.12：15 项 API 测试及 1 项真实 Tk 窗口流程测试。
- Wine 下 Windows Python 3.12.10：同一套 15 项 API 测试及 1 项窗口流程测试。
- 直接执行生成的 EXE：复制到含中文字符的临时目录，启动真实 Tk 窗口，
  离线模拟登录、查课、签到、重复点击防护、配置保存无密码及退出。
  `dist/build-verification.json` 要求 `ok=true`、`platform=win32`、`frozen=true`。
- 正常模式打开 EXE，检查窗口控件及中文显示。
- Linux 以及 Wine 下的 Windows Python 都通过保持 TLS 校验的匿名学校校时请求，
  返回 HTTP 200 / `STATUS=0` 和数值时间戳。未发送账号密码或真实签到请求。
- `git diff --check`。

## 未验证

- 原生 Windows 10 / 11 实机运行，以及系统安全软件对未签名程序的识别结果。
- ARM64 / 32 位 Windows。
- 真实学校账号登录、真实课表数据和真实签到成功率。
- GitHub Actions：已配置原生 Windows 构建工作流，远程运行结果以仓库 Actions 页面为准。

Wine 测试能够验证 Windows 打包产物及大量应用流程，但不能作为原生 Windows
实机测试的替代。接口可达也不能代表真实账号可登录或某门课程允许签到。

EXE 不包含账号、密码、会话或个人配置。分发 ZIP 同时附带对应源码与许可声明。
