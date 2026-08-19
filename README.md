# TrayOCR（托盘常驻截图 OCR）

一个轻量级后台常驻的截图 OCR 小工具：

- 全局快捷键：`Shift + C` 触发区域截图
- 框选截图后自动调用腾讯云 OCR（`GeneralAccurateOCR`）
- 识别文本自动复制到系统剪贴板
- 系统托盘常驻：可从托盘菜单进入设置 / 退出

## 运行方式（源码运行）

1. 安装依赖（建议使用官方 Python 3.10+）：

```bash
python -m pip install -r tray_ocr/requirements.txt
```

2. 启动：

```bash
python -m tray_ocr.main
```

启动后你会在系统托盘看到 `TrayOCR` 图标。

## API KEY

[腾讯云免费额度](https://cloud.tencent.com/document/product/866/35945?from=console_document_search)，[api](https://console.cloud.tencent.com/cam/capi) 获取 SecretId / SecretKey

## 使用说明

1. 右键托盘图标 → `设置`：
   - `API Endpoint`：默认 `https://ocr.tencentcloudapi.com/`
   - `Region`：例如 `ap-guangzhou`
   - `SecretId / SecretKey`：填你自己的腾讯云密钥
   - `识别接口`：下拉选择腾讯云 OCR 接口，按官方分类分组（通用文字/卡证/票据单据/文档智能/鉴伪/扫码/汽车/仅老客户续费），共 76 个；默认 `GeneralAccurateOCR`
   - `识别模式`：默认中英混合（ConfigID=OCR，精度最高）；勾选后启用多语言（ConfigID=MulOCR，自动检测中/英/日/韩等）；仅对 `GeneralAccurateOCR` 生效

2. 按 `Shift + C`：
   - 鼠标拖拽框选区域
   - 松开后自动识别
   - 识别结果自动复制到剪贴板（可直接 Ctrl+V 粘贴）

## 热键没生效怎么办

- 先确认托盘菜单里的 `截图 OCR (Shift+C)` 能否正常截图：如果菜单可以而热键不行，基本就是热键被别的软件占用或注册失败。
- 本程序优先使用 Win32 `RegisterHotKey` 注册 `Shift+C`；如果注册失败，会自动退回到“低级键盘钩子”模式兼容（启动后会弹一次提示）。
- 如果仍然不生效：建议临时关闭可能占用 `Shift+C` 的软件（输入法/截图工具/剪贴板工具/游戏键位工具等）后再试。

## 配置文件位置

配置文件保存于：`%APPDATA%\\TrayOCR\\config.json`

其中 `secret_key_encrypted` 为 DPAPI 加密后的密文（与当前 Windows 用户绑定）。

## 打包为 EXE（可选）

如果你希望分发成一个可执行文件，可以考虑 PyInstaller（体积会比较大，主要来自 Qt 运行库）：

```bash
python -m pip install pyinstaller
pyinstaller -F -w -n TrayOCR tray_ocr/main.py
```

生成物在 `dist/TrayOCR.exe`。

## 低内存占用说明

- 常驻状态不做轮询：热键通过 Win32 `RegisterHotKey` + 消息循环监听，不会持续占用 CPU。
- 只在触发时截图与网络请求：识别完成立即释放截图缓冲区。
- 若对“最低内存占用”非常敏感，可把 UI 从 Qt 换成纯 Win32（会更省内存，但开发复杂度更高）。
