"""
配置模块：统一管理 API Key、模型名等「会变、且不该写死在代码里」的东西。

为什么要单独一个文件？
- API Key 是敏感信息，绝对不能写进代码提交到 Git。
- 把配置集中在一处，以后换模型 / 换服务商只改这里，业务代码不用动。

配置来源：环境变量。开发时把它们写在 backend/.env 文件里（已加入 .gitignore，不会被提交），
python-dotenv 会在启动时自动把 .env 里的键值对加载成环境变量。
"""

# 导入 os 模块，用于访问环境变量
import os

# 导入 load_dotenv 函数，用于加载 .env 文件
from dotenv import load_dotenv

# 读取 backend/.env 文件（如果存在），把其中的 KEY=VALUE 注入到 os.environ。
# 如果环境里已经有同名变量，默认不会覆盖，所以生产环境可以直接用真实环境变量。
load_dotenv()

# ---- LLM Provider 配置（任何 OpenAI 兼容服务，改 base_url 即可切换）----
LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "deepseek")

# ---- DeepSeek 相关配置 ----

# os.getenv 取不到时返回 None，这里不设默认值，强制使用者必须配置。
# DEEPSEEK_API_KEY: str | None = os.getenv("DEEPSEEK_API_KEY")

# os.getenv 取不到返回 None，强制必须配置（校验放在 client.py，config 只负责「读」）
LLM_API_KEY: str | None = os.getenv("LLM_API_KEY")

# DeepSeek 的接口地址。DeepSeek 兼容 OpenAI 的接口格式，
# 所以我们用 OpenAI 官方 SDK，只要把 base_url 指向 DeepSeek 即可。
# DEEPSEEK_BASE_URL: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")


# 默认使用的模型。
#   deepseek-chat     : 通用对话模型（DeepSeek-V3），速度快、便宜，先用它跑通。
#   deepseek-reasoner : 推理模型（DeepSeek-R1），会先「思考」再回答，更慢更贵。
# DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
LLM_MODEL: str = os.getenv("LLM_MODEL", "deepseek-chat")
# deepseek-reasoner为带思考过程的模型
# LLM_MODEL: str = os.getenv("LLM_MODEL", "deepseek-reasoner")


# 网络行为旋钮：超时和重试次数也做成配置，不写死在代码里
LLM_TIMEOUT: float = float(os.getenv("LLM_TIMEOUT", "60"))
LLM_MAX_RETRIES: int = int(os.getenv("LLM_MAX_RETRIES", "2"))