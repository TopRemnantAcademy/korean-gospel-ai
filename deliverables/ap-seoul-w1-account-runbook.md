# AI Gospel (korean-gospel-ai) → 腾讯云首尔 (ap-seoul) W1 前置运行手册：账号与 CAM 权限

> 角色：Landing Zone 专家（landing-zone-expert）
> 范围：**仅**账号创建 + CAM 最小权限策略 + 实例角色（对应 `ap-seoul-landing-zone.md` §1 账号与权限模型）。不做产品选型、不做网络/架构设计、不写迁移实施步骤。
> 数据来源：本手册所有命令参数、CAM 服务短名、策略 action 名称、信任策略 principal、region 字符串均由 **MigraQ 技能调远端（腾讯云官方文档校验）** 获取；本环境无 AK/SK，**所有命令均未实际执行**，仅作可复制粘贴的手册。
> 执行要求：需在**已配置主账号凭证**的终端执行（建议用 break-glass 专用主账号 AK/SK，勿用日常子账号）。

---

## ⚠️ 0. 关键事实确认与偏差说明（必读）

| 项 | 结论（MigraQ 已确认） | 说明 |
|----|----------------------|------|
| 创建子账号命令 | **`tccli cam AddUser`**（不是 `CreateUser`） | TC CLI 中 CAM 没有 `CreateUser` 操作字；API 层 `cam:CreateUser` 与 `cam:AddUser` 语义等价，但 CLI 命令字是 `AddUser`，直接写 `tccli cam CreateUser` 会报 `Unknown operation`。本手册一律用 `AddUser`。 |
| Region 字符串 | **`ap-seoul`**（亚太东北·首尔），可用区 `ap-seoul-1` / `ap-seoul-2` | CAM 为全局服务，cam 命令**无需传 `--region`**；策略 resource 里的 region 写 `ap-seoul`。 |
| 策略 action 语法 | **`服务短名:动作名`**，如 `cvm:DescribeInstances` | 通配符**只能用于动作名部分**（如 `cvm:Describe*`），**不可**写成跨服务的 `name/*` 或 `*` 前缀。 |
| 虚拟 MFA | `SetMfaFlag` 中 **`LoginFlag.Stoken=1`**（软 token = 虚拟 MFA） | 同时建议开 `ActionFlag.Stoken=1`（敏感操作二次校验）。 |
| 实例角色 principal | `cvm.qcloud.com` 与 `tke.cloud.tencent.com` | 由 CVM/TKE 节点扮演，信任策略 action 为 `sts:AssumeRole`。 |
| 服务短名 | `postgres`(PG)、`redis`、`cvm`、`cbs`、`vpc`(含 NAT/EIP)、`clb`、`cos`、`cls`、`cloudaudit`、`tcr`、`ssm`、`kms` | NAT 网关动作归属 `vpc` 前缀（如 `vpc:CreateNatGateway`）。 |

> 所有 CAM 服务（CAM/CloudAudit）为全局服务，SSM/KMS/CLS/CVM/VPC/TKE 在 `ap-seoul` 均可用（MigraQ 已确认）。

---

## 1. 前置准备（tccli 配置与变量）

```bash
# 1) 安装/升级 tccli（建议 3.x 以上）
pip install --upgrade tccli

# 2) 配置主账号凭证（break-glass 专用，仅 W1 前置阶段使用）
#    方式 A：AK/SK
tccli configure set secretId "<主账号SecretId>" secretKey "<主账号SecretKey>" region ap-seoul output json
#    方式 B：OAuth 登录（推荐，避免 AK/SK 落盘）
tccli auth login

# 3) 验证可用 + 确认主账号 UIN（后续策略 resource 需用到）
tccli cam DescribeUserPermission --cli-unfold-argument --TargetUin "$(tccli cam DescribeUserInfo --output json | jq -r '.UserInfo.OwnerUin')"
```

> ⚠️ **tccli 版本/provider 对 ap-seoul 的支持**：执行前请 `tccli --version` 确认版本；若 `ap-seoul` 在某些旧版 provider 未收录，需升级 tccli。若 `jq` 未安装，下面各步骤请手动从命令回显中取 `Uin` / `PolicyId` 并替换占位符。

---

## 2. 创建 5 个子账号 + 强制开启 MFA

账号清单（与 `ap-seoul-landing-zone.md` §1.1 一致）：

| 用户名 | 用途 | 控制台登录 | API 密钥 |
|--------|------|:---:|:---:|
| `kg-ops-deploy` | 运维/部署 | ✅ | ✅ |
| `kg-db-admin` | 数据库管理（PG/Redis） | ✅ | ✅ |
| `kg-readonly` | 只读/审计查看 | ✅ | ✅ |
| `kg-cicd-role` | CI/CD 流水线 | ❌（仅 AK/SK + STS） | ✅ |
| `kg-security-audit` | 安全审计 | ✅ | ✅ |

> 密码需满足复杂度（≥8 位，含大小写+数字+特殊字符）；`NeedResetPassword 1` 强制首次登录改密。

### 2.1 创建子账号（AddUser）并捕获 UIN

```bash
# ---------- kg-ops-deploy ----------
UIN_OPS=$(tccli cam AddUser --cli-unfold-argument \
    --Name 'kg-ops-deploy' \
    --Remark 'korean-gospel-ai 首尔区 运维部署子账号' \
    --ConsoleLogin 1 --UseApi 1 --NeedResetPassword 1 \
    --Password 'OpsD3pl0y!Seoul' \
    --output json | jq -r '.Uin')

# ---------- kg-db-admin ----------
UIN_DB=$(tccli cam AddUser --cli-unfold-argument \
    --Name 'kg-db-admin' \
    --Remark 'korean-gospel-ai 首尔区 数据库管理员' \
    --ConsoleLogin 1 --UseApi 1 --NeedResetPassword 1 \
    --Password 'DbAdm1n!Seoul' \
    --output json | jq -r '.Uin')

# ---------- kg-readonly ----------
UIN_RO=$(tccli cam AddUser --cli-unfold-argument \
    --Name 'kg-readonly' \
    --Remark 'korean-gospel-ai 首尔区 只读审计' \
    --ConsoleLogin 1 --UseApi 1 --NeedResetPassword 1 \
    --Password 'Read0nly!Seoul' \
    --output json | jq -r '.Uin')

# ---------- kg-cicd-role（禁止控制台登录，仅 AK/SK）----------
UIN_CICD=$(tccli cam AddUser --cli-unfold-argument \
    --Name 'kg-cicd-role' \
    --Remark 'korean-gospel-ai 首尔区 CI/CD 流水线' \
    --ConsoleLogin 0 --UseApi 1 --NeedResetPassword 0 \
    --Password 'CicdR0le!Seoul' \
    --output json | jq -r '.Uin')

# ---------- kg-security-audit ----------
UIN_AUDIT=$(tccli cam AddUser --cli-unfold-argument \
    --Name 'kg-security-audit' \
    --Remark 'korean-gospel-ai 首尔区 安全审计' \
    --ConsoleLogin 1 --UseApi 1 --NeedResetPassword 1 \
    --Password 'Aud1t!Seoul' \
    --output json | jq -r '.Uin')

echo "OPS=$UIN_OPS DB=$UIN_DB RO=$UIN_RO CICD=$UIN_CICD AUDIT=$UIN_AUDIT"
```

> ⚠️ 若 `jq` 不可用，去掉 `| jq -r '.Uin'`，从回显 JSON 的 `Uin` 字段取值，后续用实际 UIN 替换。

### 2.2 强制开启虚拟 MFA（SetMfaFlag）

> 对**每个**子账号执行。下面用变量循环；如手动执行，把 `$UIN_*` 换成实际 UIN。

```bash
for U in "$UIN_OPS" "$UIN_DB" "$UIN_RO" "$UIN_CICD" "$UIN_AUDIT"; do
  # 登录保护：开启虚拟 MFA（软 token）
  tccli cam SetMfaFlag --cli-unfold-argument \
      --OpUin "$U" \
      --LoginFlag.Stoken 1 --LoginFlag.Phone 0 --LoginFlag.Wechat 0
  # 操作保护：敏感操作二次 MFA 校验（建议开启）
  tccli cam SetMfaFlag --cli-unfold-argument \
      --OpUin "$U" \
      --ActionFlag.Stoken 1 --ActionFlag.Phone 0 --ActionFlag.Wechat 0
done
```

**控制台等价动作**（备用，无需 CLI）：CAM 控制台 → 用户 → 对应用户 → 「安全」→ 绑定虚拟 MFA 设备（如腾讯云 MFA App / Google Authenticator）→ 在「登录保护」「操作保护」中开启 MFA。

---

## 3. 各子账号最小权限 CAM 策略（CreatePolicy + AttachUserPolicy）

> **约定**：每个策略 JSON 作为独立文件保存（避免 shell 转义问题），再用 `$(cat 文件)` 喂给 `--PolicyDocument`。
> PowerShell 用户把 `$(cat x.json)` 替换为 `$(Get-Content x.json -Raw)`。
> resource 中的 `<MAIN_UIN>` 替换为主账号 UIN；全局服务（CAM/CloudAudit）region 写 `*`。

### 3.1 db-admin —— 仅 PostgreSQL / Redis 管理

`db-admin-policy.json`：

```json
{
  "version": "2.0",
  "statement": [
    {
      "effect": "allow",
      "action": [
        "postgres:CreateInstances", "postgres:DescribeDBInstances", "postgres:DescribeInstances",
        "postgres:DescribeDBInstanceAttribute", "postgres:DescribeDBBackups", "postgres:CreateDBBackup",
        "postgres:RestoreDBInstanceObjects", "postgres:ModifyDBInstanceName", "postgres:ModifyDBInstanceSpec",
        "postgres:ModifyDBInstanceDeployment", "postgres:DescribeAccounts", "postgres:CreateAccount",
        "postgres:ModifyAccountRemark", "postgres:ResetAccountPassword", "postgres:DescribeSlowQueryList",
        "postgres:DescribeSlowQueryAnalysis", "postgres:UpgradeDBInstance", "postgres:UpgradeDBInstanceMajorVersion",
        "postgres:UpgradeDBInstanceKernelVersion", "postgres:DescribeDBVersions", "postgres:DescribeProductConfig",
        "postgres:DescribeRegions", "postgres:DescribeZones",
        "redis:CreateInstances", "redis:DescribeInstances", "redis:DescribeInstanceBackups",
        "redis:ManualBackupInstance", "redis:RestoreInstance", "redis:ModifyInstance", "redis:ModifyInstanceName",
        "redis:UpgradeInstance", "redis:UpgradeInstanceVersion", "redis:ModifyInstancePassword", "redis:ResetPassword",
        "redis:DescribeTaskList", "redis:DescribeInstanceShards", "redis:DescribeInstanceAccount",
        "redis:CreateInstanceAccount", "redis:ModifyInstanceAccount", "redis:DescribeSlowLog",
        "redis:DescribeProxySlowLog", "redis:DescribeProductInfo", "redis:DescribeMaintenanceWindow",
        "redis:ModifyMaintenanceWindow", "redis:CreateParamTemplate", "redis:DescribeParamTemplates",
        "redis:DescribeInstanceParams", "redis:ModifyInstanceParams"
      ],
      "resource": ["*"]
    }
  ]
}
```

```bash
PID_DB=$(tccli cam CreatePolicy --cli-unfold-argument \
    --PolicyName 'kg-db-admin' \
    --Description 'korean-gospel-ai 首尔区 仅 PostgreSQL/Redis 管理' \
    --PolicyDocument "$(cat db-admin-policy.json)" \
    --output json | jq -r '.PolicyId')

tccli cam AttachUserPolicy --cli-unfold-argument --AttachUin "$UIN_DB" --PolicyId "$PID_DB"
```

### 3.2 readonly —— 全局只读（禁止任何写操作）

`readonly-policy.json`：

```json
{
  "version": "2.0",
  "statement": [
    {
      "effect": "allow",
      "action": [
        "cvm:Describe*", "cbs:Describe*", "vpc:Describe*", "clb:Describe*",
        "postgres:Describe*", "redis:Describe*",
        "cos:Get*", "cos:Head*", "cos:List*", "cos:Describe*",
        "cls:Describe*", "cls:SearchLog", "cls:Metrics*",
        "cloudaudit:Describe*", "cloudaudit:List*", "cloudaudit:LookUpEvents", "cloudaudit:Get*",
        "kms:Describe*", "kms:List*", "kms:Get*",
        "ssm:Describe*", "ssm:Get*", "ssm:List*",
        "tcr:Describe*", "nat:Describe*", "monitor:Describe*", "monitor:Get*",
        "tag:Describe*", "tag:Get*", "cam:Describe*", "cam:Get*", "cam:List*"
      ],
      "resource": ["*"]
    }
  ]
}
```

```bash
PID_RO=$(tccli cam CreatePolicy --cli-unfold-argument \
    --PolicyName 'kg-readonly' \
    --Description 'korean-gospel-ai 首尔区 全局只读' \
    --PolicyDocument "$(cat readonly-policy.json)" \
    --output json | jq -r '.PolicyId')

tccli cam AttachUserPolicy --cli-unfold-argument --AttachUin "$UIN_RO" --PolicyId "$PID_RO"
```

> 说明：`cos:Get*` 覆盖 `GetObject`/`GetBucket*`；`cos:List*` 覆盖 `ListBuckets`/`ListParts`；`cloudaudit:LookUpEvents` 为审计日志查询专用动作（不在 `Describe*` 通配内）。

### 3.3 security-audit —— 仅读 CloudAudit/CLS，显式 Deny 删除审计日志

`security-audit-policy.json`：

```json
{
  "version": "2.0",
  "statement": [
    {
      "effect": "allow",
      "action": [
        "cloudaudit:Describe*", "cloudaudit:List*", "cloudaudit:LookUpEvents",
        "cloudaudit:Get*", "cloudaudit:InquireAuditCredit",
        "cls:Describe*", "cls:SearchLog", "cls:Metrics*", "cls:Get*", "cls:List*"
      ],
      "resource": ["*"]
    },
    {
      "effect": "deny",
      "action": [
        "cloudaudit:Delete*", "cloudaudit:Create*", "cloudaudit:Modify*",
        "cloudaudit:Update*", "cloudaudit:StartLogging", "cloudaudit:StopLogging",
        "cls:Delete*", "cls:Create*", "cls:Modify*"
      ],
      "resource": ["*"]
    }
  ]
}
```

```bash
PID_AUDIT=$(tccli cam CreatePolicy --cli-unfold-argument \
    --PolicyName 'kg-security-audit' \
    --Description 'korean-gospel-ai 首尔区 安全审计 仅读+显式Deny删审计' \
    --PolicyDocument "$(cat security-audit-policy.json)" \
    --output json | jq -r '.PolicyId')

tccli cam AttachUserPolicy --cli-unfold-argument --AttachUin "$UIN_AUDIT" --PolicyId "$PID_AUDIT"
```

> 说明：`cloudaudit:Delete*` 覆盖 `DeleteAudit`/`DeleteAuditTrack`；`cls:Delete*` 覆盖 `DeleteTopic`/`DeleteIndex`/`DeleteAlarm` 等。Deny 优先于同账号任何 Allow，确保审计日志不可被该账号删除。

### 3.4 cicd-role —— 仅 CI/CD（TCR 镜像 + 写 CLS）

`cicd-role-policy.json`：

```json
{
  "version": "2.0",
  "statement": [
    {
      "effect": "allow",
      "action": [
        "tcr:PushRepository", "tcr:PullRepository", "tcr:Describe*", "tcr:CreateRepository",
        "tcr:DeleteRepository", "tcr:ModifyRepository", "tcr:DescribeRepositories", "tcr:DescribeImages",
        "tcr:DeleteImage", "tcr:DescribeNamespaces", "tcr:CreateNamespace", "tcr:ManageImageLifecycle",
        "tcr:CreateImageRetention", "tcr:DescribeImageRetention", "tcr:ModifyImageRetention",
        "tcr:CreateWebhookTrigger", "tcr:DescribeWebhookTrigger", "tcr:ModifyWebhookTrigger",
        "tcr:DeleteWebhookTrigger", "tcr:DescribeWebhookTriggerLog",
        "cls:PushLog", "cls:UploadLog", "cls:DescribeTopics", "cls:DescribeLogsets",
        "cls:DescribeIndex", "cls:CreateLogset", "cls:CreateTopic", "cls:ModifyTopic",
        "cls:ModifyIndex", "cls:CreateIndex"
      ],
      "resource": ["*"]
    }
  ]
}
```

```bash
PID_CICD=$(tccli cam CreatePolicy --cli-unfold-argument \
    --PolicyName 'kg-cicd-role' \
    --Description 'korean-gospel-ai 首尔区 CI/CD 仅镜像推送与写日志' \
    --PolicyDocument "$(cat cicd-role-policy.json)" \
    --output json | jq -r '.PolicyId')

tccli cam AttachUserPolicy --cli-unfold-argument --AttachUin "$UIN_CICD" --PolicyId "$PID_CICD"
```

> 说明：`cls:PushLog` 为 CLS 结构化日志上传动作；`tcr:PushRepository` 为镜像推送核心动作。若 CI 还需触发 TKE 部署，按需追加 `tke:*` / `scf:*`（⚠️ 见末尾待复核项）。

### 3.5 ops-deploy —— 部署权限（CVM/CBS/VPC/CLB/NAT/COS 管理）

`ops-deploy-policy.json`：

```json
{
  "version": "2.0",
  "statement": [
    {
      "effect": "allow",
      "action": [
        "cvm:Describe*", "cvm:RunInstances", "cvm:StartInstances", "cvm:StopInstances",
        "cvm:RebootInstances", "cvm:TerminateInstances", "cvm:ModifyInstancesAttribute",
        "cvm:ResetInstance", "cvm:CreateImage", "cvm:DeleteImages", "cvm:ModifyImageAttribute",
        "cvm:DescribeImages", "cvm:AttachDisks", "cvm:DetachDisks",
        "cvm:CreateKeyPair", "cvm:DeleteKeyPairs", "cvm:AssociateInstancesKeyPairs", "cvm:DisassociateInstancesKeyPairs",
        "cbs:Describe*", "cbs:CreateDisks", "cbs:AttachDisks", "cbs:DetachDisks",
        "cbs:ModifyDiskAttributes", "cbs:ResizeDisk", "cbs:TerminateDisks", "cbs:CreateSnapshot",
        "cbs:DeleteSnapshots", "cbs:ApplySnapshot",
        "vpc:Describe*", "vpc:CreateVpc", "vpc:DeleteVpc", "vpc:ModifyVpcAttribute",
        "vpc:CreateSubnet", "vpc:DeleteSubnet", "vpc:ModifySubnetAttribute",
        "vpc:CreateSecurityGroup", "vpc:DeleteSecurityGroup", "vpc:ModifySecurityGroupPolicies",
        "vpc:CreateSecurityGroupPolicies", "vpc:DeleteSecurityGroupPolicies",
        "vpc:CreateNetworkInterface", "vpc:DeleteNetworkInterface", "vpc:AttachNetworkInterface",
        "vpc:DetachNetworkInterface", "vpc:AssignPrivateIpAddresses", "vpc:UnassignPrivateIpAddresses",
        "vpc:CreateRouteTable", "vpc:DeleteRouteTable", "vpc:CreateRoutes", "vpc:DeleteRoutes",
        "vpc:ModifyRouteTableAttribute", "vpc:CreateEip", "vpc:DeleteEip", "vpc:AssociateAddress",
        "vpc:DisassociateAddress", "vpc:ModifyAddressAttribute",
        "vpc:CreateNatGateway", "vpc:DeleteNatGateway", "vpc:ModifyNatGatewayAttribute",
        "vpc:CreateNatGatewayDestinationIpPortTranslationNatRule", "vpc:DeleteNatGatewayDestinationIpPortTranslationNatRule",
        "clb:Describe*", "clb:CreateLoadBalancer", "clb:DeleteLoadBalancer", "clb:ModifyLoadBalancerAttributes",
        "clb:CreateListener", "clb:DeleteListener", "clb:ModifyListener", "clb:CreateRule", "clb:DeleteRule",
        "clb:ModifyRule", "clb:RegisterTargets", "clb:DeregisterTargets", "clb:ModifyTargetPort",
        "clb:ModifyTargetWeight", "clb:SetLoadBalancerSecurityGroups", "clb:SetSecurityGroupForLoadbalancers",
        "clb:CreateTargetGroup", "clb:DeleteTargetGroup", "clb:AssociateTargetGroups", "clb:DisassociateTargetGroups",
        "clb:AutoRewrite", "clb:SetLoadBalancerClsLog",
        "cos:Put*", "cos:Get*", "cos:Head*", "cos:List*", "cos:Delete*", "cos:Post*", "cos:Options*",
        "cos:Restore*", "cos:Describe*", "cos:CreateBucket", "cos:DeleteBucket",
        "cos:PutBucketAcl", "cos:PutBucketCORS", "cos:PutBucketLifecycle", "cos:PutBucketPolicy",
        "cos:PutBucketVersioning", "cos:PutBucketEncryption", "cos:PutBucketTagging", "cos:PutBucketWebsite",
        "cos:PutBucketIntelligentTiering", "cos:PutObjectAcl", "cos:PutObjectTagging",
        "cos:GetBucketAcl", "cos:GetBucketCORS", "cos:GetBucketLifecycle", "cos:GetBucketPolicy",
        "cos:GetBucketVersioning", "cos:GetBucketWebsite", "cos:GetBucketTagging", "cos:GetBucketEncryption",
        "cos:GetObjectAcl", "cos:GetObjectTagging", "cos:DeleteBucketCORS", "cos:DeleteBucketLifecycle",
        "cos:DeleteBucketPolicy", "cos:DeleteBucketTagging", "cos:Replication*"
      ],
      "resource": ["*"]
    }
  ]
}
```

```bash
PID_OPS=$(tccli cam CreatePolicy --cli-unfold-argument \
    --PolicyName 'kg-ops-deploy' \
    --Description 'korean-gospel-ai 首尔区 部署 CVM/CBS/VPC/CLB/NAT/COS' \
    --PolicyDocument "$(cat ops-deploy-policy.json)" \
    --output json | jq -r '.PolicyId')

tccli cam AttachUserPolicy --cli-unfold-argument --AttachUin "$UIN_OPS" --PolicyId "$PID_OPS"
```

> ⚠️ **TKE 演进**：当项目由 CVM 演进到 TKE 时，ops-deploy 需追加 `tke:*` 管理动作（如 `tke:CreateCluster`/`tke:Describe*`/`tke:ModifyCluster` 等）。本 W1 阶段按 landing-zone §1.2 先覆盖 CVM 形态；TKE 动作名以控制台/MigraQ 复核为准。

---

## 4. CAM 实例角色（供 CVM/TKE 节点使用）

> 用途：CVM/TKE 节点绑定该角色后，用**临时凭证**访问 SSM（读密钥）、CLS（写日志）、KMS（解密）、COS（读备份桶），避免静态 AK/SK 落盘。

### 4.1 信任策略（允许 CVM/TKE 扮演）

`instance-role-trust.json`：

```json
{
  "version": "2.0",
  "statement": [
    {
      "action": "name/sts:AssumeRole",
      "effect": "allow",
      "principal": {
        "service": ["cvm.qcloud.com", "tke.cloud.tencent.com"]
      }
    }
  ]
}
```

```bash
ROLE_NAME='kg-node-role'
tccli cam CreateRole --cli-unfold-argument \
    --RoleName "$ROLE_NAME" \
    --Description 'korean-gospel-ai 首尔区 CVM/TKE 节点实例角色' \
    --ConsoleLogin 0 \
    --SessionDuration 43200 \
    --PolicyDocument "$(cat instance-role-trust.json)"
```

### 4.2 角色权限策略（SSM 读 + CLS 写 + KMS 解密 + COS 读备份桶）

`instance-role-policy.json`（**resource 已限定，非 `*`**）：

```json
{
  "version": "2.0",
  "statement": [
    {
      "effect": "allow",
      "action": [
        "ssm:GetSecretValue", "ssm:DescribeSecret", "ssm:ListSecrets", "ssm:GetRegions",
        "cls:PushLog", "cls:UploadLog", "cls:DescribeTopics", "cls:DescribeLogsets", "cls:DescribeIndex",
        "kms:Decrypt", "kms:DescribeKey", "kms:DescribeKeys", "kms:GetKeyRotationStatus", "kms:ListKeys", "kms:ListKeyDetail",
        "cos:GetObject", "cos:HeadObject", "cos:GetBucket", "cos:ListBucket",
        "cos:GetBucketLocation", "cos:GetBucketVersioning", "cos:GetObjectTagging", "cos:GetObjectAcl", "cos:GetBucketAcl"
      ],
      "resource": [
        "qcs::ssm::uin/<MAIN_UIN>:secret/<YOUR_SECRET_NAME>",
        "qcs::kms::uin/<MAIN_UIN>:key/<YOUR_KEY_ID>",
        "qcs::cos::uin/<MAIN_UIN>:<YOUR_BACKUP_BUCKET>-<YOUR_APPID>/*",
        "qcs::cls::*"
      ]
    }
  ]
}
```

```bash
# 创建角色策略
PID_ROLE=$(tccli cam CreatePolicy --cli-unfold-argument \
    --PolicyName 'kg-node-role-policy' \
    --Description '节点角色 SSM读/CLS写/KMS解密/COS读备份' \
    --PolicyDocument "$(cat instance-role-policy.json)" \
    --output json | jq -r '.PolicyId')

# 绑定到角色（用 PolicyName + AttachRoleName 二选一）
tccli cam AttachRolePolicy --cli-unfold-argument \
    --PolicyName 'kg-node-role-policy' \
    --AttachRoleName "$ROLE_NAME"
```

> ⚠️ 占位符替换：`<MAIN_UIN>`=主账号 UIN；`<YOUR_SECRET_NAME>`=SSM 密钥名；`<YOUR_KEY_ID>`=KMS 密钥 ID；`<YOUR_BACKUP_BUCKET>`/`<YOUR_APPID>`=COS 备份桶名与 APPID。若先不确定，可临时把 resource 写为 `*` 再收紧（不推荐长期 `*`）。
> ⚠️ `SessionDuration` 上限（默认 43200 秒=12h）以控制台/MigraQ 复核为准。

### 4.3 将实例角色绑定到 CVM/TKE 节点

```bash
# CVM：创建/修改实例时绑定（--CamRoleName）
tccli cvm RunInstances --cli-unfold-argument --CamRoleName "$ROLE_NAME"  #（其余参数略，属部署阶段）

# TKE：节点池创建时指定 roleName（属部署阶段，⚠️ 具体字段以 TKE 文档为准）
```

> 角色绑定动作本身属部署阶段（W2+），W1 仅完成角色与策略创建。此处给出绑定示意。

---

## 5. 执行前检查清单（Pre-flight）

- [ ] `tccli --version` 已确认，且 provider 支持 `ap-seoul`（⚠️ 见末尾）。
- [ ] 已用 **break-glass 主账号** 凭证配置 tccli（`configure` 或 `auth login`），非日常子账号。
- [ ] 已记录**主账号 UIN**（`<MAIN_UIN>`），用于策略 resource ARN。
- [ ] 已确定 COS 备份桶名 + APPID、SSM 密钥名、KMS 密钥 ID（用于实例角色 resource 限定）。
- [ ] 各子账号初始密码已按复杂度要求准备（≥8 位，大小写+数字+特殊字符）。
- [ ] 已规划 MFA 绑定方式（虚拟 MFA App），并通知各账号持有人扫码绑定。
- [ ] 已确认 `ap-seoul` region 字符串 = `ap-seoul`（MigraQ 已确认，仍建议控制台复核）。
- [ ] 已备份现有 CAM 策略/角色（如有），避免覆盖。
- [ ] `jq` 可用，或已准备手动从回显提取 `Uin`/`PolicyId`。

---

## 6. 执行后验证步骤（Post-validation）

### 6.1 验证 MFA 已开启

```bash
tccli cam GetUserMfaFlag --cli-unfold-argument --OpUin "$UIN_OPS"
# 期望 LoginFlag.Stoken=1（虚拟 MFA 已启用）
```

### 6.2 验证 readonly 权限边界（应允许读、拒绝写）

```bash
# 用 kg-readonly 的 AK/SK 配置一个临时 profile 后验证
tccli configure set secretId "<readonly_SecretId>" secretKey "<readonly_SecretKey>" profile kg-readonly

# ✅ 允许：只读查询
tccli cvm DescribeInstances --profile kg-readonly --region ap-seoul

# ❌ 应被拒绝：尝试写操作
tccli cvm RunInstances --profile kg-readonly --region ap-seoul --InstanceChargeType POSTPAID_BY_HOUR
# 期望返回 AuthFailure.UnauthorizedOperation（无 cvm:RunInstances 权限）
```

### 6.3 验证 security-audit 不可删审计

```bash
tccli configure set secretId "<audit_SecretId>" secretKey "<audit_SecretKey>" profile kg-audit

# ✅ 允许：读 CloudAudit
tccli cloudaudit LookUpEvents --profile kg-audit --region ap-seoul

# ❌ 应被拒绝：删除审计
tccli cloudaudit DeleteAudit --profile kg-audit --region ap-seoul --AuditName "<AUDIT_NAME>"
# 期望返回 AuthFailure（Deny cloudaudit:Delete* 生效）
```

### 6.4 验证实例角色可经 SSM 拉取密钥（GetSecret）

```bash
# 在已绑定 kg-node-role 的 CVM/TKE 节点内执行（无需配置 AK/SK，临时凭证由元数据自动提供）
tccli ssm GetSecretValue --SecretName "<YOUR_SECRET_NAME>" --region ap-seoul
# 期望返回密钥明文/密文 → 实例角色 SSM 读权限生效

# 同时验证 KMS 解密与 CLS 写（由应用/agent 调用，命令行可抽样）
tccli kms Decrypt --region ap-seoul --CiphertextBlob "<BASE64>"   # 期望成功
```

### 6.5 验证策略绑定结果

```bash
tccli cam ListAttachedUserPolicies --cli-unfold-argument --TargetUin "$UIN_DB"   # 应仅 kg-db-admin
tccli cam ListAttachedRolePolicies --cli-unfold-argument --RoleName "$ROLE_NAME" # 应仅 kg-node-role-policy
```

---

## 7. ⚠️ 待复核项（执行前/执行中需控制台或 MigraQ 二次确认）

1. **`ap-seoul` 精确 region 字符串**：MigraQ 已确认 = `ap-seoul`，可用区 `ap-seoul-1/2`。仍建议在 CAM/VPC 控制台最终复核区域名与可用区数量。
2. **tccli 版本 / provider 对 ap-seoul 的支持**：旧版 tccli 可能未收录 `ap-seoul`，执行前 `tccli --version` + 升级；若 `region ap-seoul` 报未知区域需更新 provider。
3. **`AddUser` vs `CreateUser`**：任务示例写 `CreateUser`，实际 TC CLI 命令字是 `AddUser`（已在本手册修正）。若未来 tccli 版本变更，以 `tccli cam help` 实时输出为准。
4. **CAM 服务短名**：本手册 action 均经 MigraQ 校验（`postgres`/`redis`/`cvm`/`cbs`/`vpc`/`clb`/`cos`/`cls`/`cloudaudit`/`tcr`/`ssm`/`kms`）。若某动作名在你账号版本报错，以 CAM 控制台「策略语法」自动补全或 MigraQ 复核为准。
5. **实例角色 resource 限定**：SSM 密钥名、KMS 密钥 ID、COS 备份桶名/APPID 需替换为实际值；不确定时勿长期用 `*`。
6. **TKE 节点角色绑定字段**：`tke.cloud.tencent.com` 作为 principal 已确认；但 TKE 节点池绑定角色的具体 API 字段（如 `RoleName`）以 TKE 官方文档/MigraQ 复核为准（属 W2 部署阶段）。
7. **`SessionDuration` 上限**：实例角色会话时长 43200s 是否达上限，以控制台/MigraQ 复核为准。
8. **CI/CD 触发部署额外权限**：若 CI 流水线需触发 TKE 部署（`tke:*`）或 SCF，需在 `kg-cicd-role` 追加相应 action（⚠️ 未含在本 W1 策略）。
9. **MFA 物理/虚拟绑定流程**：`SetMfaFlag` 仅设置「要求 MFA」标志，子账号首次登录仍需在控制台/App **完成 MFA 设备绑定**才真正生效——需纳入 W1 收尾动作并通知账号持有人。

---

*本运行手册为 W1（前置）阶段交付，仅覆盖账号与 CAM 权限（对应 `ap-seoul-landing-zone.md` §1）。网络/VPC/安全组/日志/合规落地见主着陆区设计文档；资源创建与部署见后续 W2+ 实施文档。所有命令参数与策略 action 均经 MigraQ 调远端校验，未在本环境实际执行。*
