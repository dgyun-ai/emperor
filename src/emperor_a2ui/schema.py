"""A2UI schema manager integration for agent prompts."""

from __future__ import annotations

from functools import lru_cache

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.constants import VERSION_0_9
from a2ui.schema.manager import A2uiSchemaManager


@lru_cache(maxsize=1)
def _schema_manager() -> A2uiSchemaManager:
    return A2uiSchemaManager(
        version=VERSION_0_9,
        catalogs=[BasicCatalog.get_config(version=VERSION_0_9)],
    )


def build_a2ui_system_prompt(*, language: str = "zh") -> str:
    """Generate system-prompt instructions for A2UI-capable agents."""
    if language == "zh":
        role = (
            "你可以使用 render_a2ui 工具向用户展示丰富的交互式界面（表单、卡片、按钮等）。"
            "当用户需要选择、填写信息或查看结构化内容时，优先调用 render_a2ui 而不是仅用纯文本描述。"
        )
        ui_rules = """
- 使用 A2UI v0.9 协议消息（createSurface、updateComponents、updateDataModel、deleteSurface）。
- 每个 surface 需要唯一的 surfaceId；建议使用 `{turn_id}-main` 格式。
- createSurface 的 catalogId 使用 basic catalog 默认值。
- 每个 surface 必须包含 id 为 root 的组件作为根节点。
- TextField、CheckBox、Slider、DateTimeInput、ChoicePicker 等可输入组件必须为 value 绑定 data model 路径（例如 `"value": {"path": "/fields/email"}`），并发送 updateDataModel 初始化对应字段。
- 用户点击按钮或提交表单后，你会收到 A2UI Action 消息（含 ```a2ui_action JSON 块``` 与 dataModel 快照）；请解析 JSON 块中的 context/dataModel，据此更新界面或继续对话。
- 仅在需要交互式 UI 时调用 render_a2ui；普通问答仍用 markdown 文本回复。
""".strip()
    else:
        role = (
            "You can use the render_a2ui tool to present rich interactive UIs "
            "(forms, cards, buttons). Prefer render_a2ui over plain text when the user "
            "needs to choose, fill in information, or view structured content."
        )
        ui_rules = """
- Use A2UI v0.9 messages (createSurface, updateComponents, updateDataModel, deleteSurface).
- Each surface needs a unique surfaceId; prefer `{turn_id}-main`.
- Use the default basic catalog for createSurface.catalogId.
- Include a component with id `root` as the tree root for each surface.
- Input components (TextField, CheckBox, Slider, DateTimeInput, ChoicePicker) must bind `value` to a data-model path (e.g. `"value": {"path": "/fields/email"}`) and send updateDataModel to initialize fields.
- After the user clicks a button or submits a form you will receive an A2UI Action message (with a fenced ```a2ui_action``` JSON block and dataModel snapshot); parse context/dataModel from the JSON block and update the UI or continue accordingly.
- Call render_a2ui only when an interactive UI is needed; otherwise reply with markdown text.
""".strip()

    return _schema_manager().generate_system_prompt(
        role_description=role,
        ui_description=ui_rules,
        include_schema=True,
        include_examples=True,
        validate_examples=True,
    )
