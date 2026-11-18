# iOS 真机云验收 / iOS Cloud Device Provider Acceptance

## 1. 用途

当本机没有 macOS 或没有可用真机时，通过 Appium 设备云完成真实 iPhone 上的
session、WDA 和 smoke 验收。设备云真机可以关闭物理设备门，但不能替代
Simulator 多版本、Xcode 诊断和本地设备信任学习。

当前默认 provider 为 BrowserStack，同时支持 Sauce Labs 和 LambdaTest 的
capability 命名空间。三者都要求预先上传测试 App，并取得 vendor app ID。

## 2. 安全边界

- 只上传测试构建，不上传生产 App、生产签名或个人数据。
- 云账号只进入本地 `.env` 或 GitHub Secrets，不写入仓库和报告。
- 只使用最少权限的测试账号，会话结束后撤销临时 Key。
- 日志、截图和 page source 视为不可信输入。
- 系统权限、通知、文件、WebView 等能力按 provider 和设备实际支持情况验收。

## 3. 必需配置

| 配置 / Setting | 用途 / Purpose |
| --- | --- |
| `QA_IOS_DEVICE_PROVIDER` | `browserstack`、`saucelabs` 或 `lambdatest` |
| `QA_IOS_CLOUD_REMOTE_URL` | provider Appium endpoint |
| `QA_IOS_CLOUD_USER` | 云账号用户名 |
| `QA_IOS_CLOUD_ACCESS_KEY` | 云账号访问 Key，作为 Secret |
| `QA_IOS_CLOUD_APP` | 已上传 App 的 provider ID |
| `QA_IOS_CLOUD_DEVICE_NAME` | 例如 `iPhone 15` |
| `QA_IOS_CLOUD_PLATFORM_VERSION` | 例如 `17` |

GitHub Actions 使用：

```text
IOS_CLOUD_USER
IOS_CLOUD_ACCESS_KEY
IOS_CLOUD_APP
```

配置命令只写入 Secret 名称，不在终端回显值：

```powershell
gh secret set IOS_CLOUD_USER
gh secret set IOS_CLOUD_ACCESS_KEY
gh secret set IOS_CLOUD_APP
```

## 4. BrowserStack 首次准备

1. 创建 BrowserStack App Automate 测试账号。
2. 准备一个签名的测试 `.ipa`，或先使用 provider 提供的测试 App。
3. 通过 BrowserStack 控制台或上传 API 上传 App。
4. 保存返回的 `bs://...` app ID。
5. 将用户名、Access Key 和 app ID 设置到 GitHub Secrets。
6. 选择真实 iPhone 的 device name 和 platform version。
7. 触发 `iOS Cloud Device Smoke` workflow。

App 上传 API 的凭据只通过环境变量或 Secret 注入，不能写进命令历史或文档。

## 5. 本地连接

```powershell
$env:QA_IOS_DEVICE_PROVIDER="browserstack"
$env:QA_IOS_CLOUD_REMOTE_URL="https://hub-cloud.browserstack.com/wd/hub"
$env:QA_IOS_CLOUD_USER="<from-secret-store>"
$env:QA_IOS_CLOUD_ACCESS_KEY="<from-secret-store>"
$env:QA_IOS_CLOUD_APP="bs://<uploaded-app-id>"
$env:QA_IOS_CLOUD_DEVICE_NAME="iPhone 15"
$env:QA_IOS_CLOUD_PLATFORM_VERSION="17"

$env:PYTEST_DEBUG_TEMPROOT="$PWD\.tmp-pytest"
.\.venv\Scripts\python.exe -m pytest tests\ios -q -p no:cacheprovider
```

不要把 `<from-secret-store>` 替换成真实值后提交或发送到聊天。

## 6. CI 连接

GitHub `workflow_dispatch` 只在 workflow 已存在于默认分支后，才能从 Actions
或 CLI 直接触发。因此 `ios-cloud-smoke.yml` 需要先经过正常评审和合并；不能
在只存在于 feature branch 时用 `gh workflow run` 调用。

```powershell
gh workflow run ios-cloud-smoke.yml `
  -f provider=browserstack `
  -f device_name="iPhone 15" `
  -f platform_version=17 `
  -f remote_url="https://hub-cloud.browserstack.com/wd/hub"

gh run watch <run-id> --exit-status
```

通过标准：

- Secret 预检通过。
- 云端真实 iPhone 分配成功。
- Appium session 创建成功。
- 窗口尺寸读取成功。
- session 正常退出。
- pytest smoke 通过。
- Allure 和 provider 日志已上传。

## 7. 故障分层

| 现象 / Symptom | 首先检查 / First Check |
| --- | --- |
| Secret 缺失 | GitHub Secrets 名称是否完全一致 |
| 401 / 403 | 云账号 Key、权限和过期时间 |
| App not found | app ID 是否属于当前账号，App 是否仍可用 |
| Device unavailable | device name、platform version 和 provider 配额 |
| Session 超时 | 设备启动时间、provider 状态和 App 启动速度 |
| App 安装失败 | IPA 签名、设备类型、系统版本和 App 构建 |
| Session 创建但测试失败 | 测试代码、权限、system UI 和 App 行为 |

设备云失败必须先分类为凭据、配额、App、设备、Driver 或测试失败。`NOT RUN`
和 cloud setup failure 不得写成 `PASS`。

## 8. 当前状态

截至 2026-10-31：

- 代码和 capability adapter 已准备并通过。
- BrowserStack Username/Access Key 已配置。
- BrowserStack sample App `bs://sample.app` 已在 iPhone 14 / iOS 16 上通过
  Appium session（Run `41173821288`）。
- 项目自己的测试 App 尚未上传，`IOS_CLOUD_APP` 尚未配置。

云环境和凭据已经验证；项目 App 验收通过前，不能把项目真机覆盖标记为完成。
