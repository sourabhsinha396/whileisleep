from django.db import migrations, models


def to_tree(rule) -> dict:
    """The four fixed conditions a rule had, as a tree. All that were set had to hold."""
    tests = []
    if rule.intent:
        tests.append({"field": "message.intent", "op": "equals", "value": rule.intent})
    keywords = [line.strip() for line in rule.keywords.splitlines() if line.strip()]
    if keywords:
        # "contains_any" is what the old matching did: a substring, ignoring case.
        tests.append({"field": "message.text", "op": "contains_any", "value": keywords[:50]})
    if rule.page_contains:
        tests.append({"field": "page.url", "op": "contains", "value": rule.page_contains})
    if rule.first_message_only:
        tests.append({"field": "message.is_first", "op": "equals", "value": True})
    # A rule with no condition never matched; keep it that way.
    return {"all": tests or [{"field": "message.intent", "op": "equals", "value": "never-matches"}]}


def to_actions(rule) -> list:
    actions = []
    if rule.tag.strip():
        actions.append({"type": "tag", "value": rule.tag.strip()})
    if rule.handoff:
        actions.append({"type": "handoff"})
    if rule.reply.strip():
        actions.append({"type": "reply", "text": rule.reply})
    elif rule.ai_instruction.strip():
        actions.append({"type": "instruct", "text": rule.ai_instruction})
    return actions


def convert_rules(apps, schema_editor):
    Rule = apps.get_model("agent", "Rule")
    for rule in Rule.objects.all():
        rule.conditions = to_tree(rule)
        rule.actions = to_actions(rule)
        rule.save(update_fields=["conditions", "actions"])


class Migration(migrations.Migration):
    dependencies = [
        ("agent", "0005_turn"),
    ]

    operations = [
        migrations.AddField(
            model_name="rule",
            name="conditions",
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name="rule",
            name="actions",
            field=models.JSONField(default=list),
        ),
        migrations.RunPython(convert_rules, migrations.RunPython.noop),
        migrations.RemoveField(model_name="rule", name="intent"),
        migrations.RemoveField(model_name="rule", name="keywords"),
        migrations.RemoveField(model_name="rule", name="page_contains"),
        migrations.RemoveField(model_name="rule", name="first_message_only"),
        migrations.RemoveField(model_name="rule", name="reply"),
        migrations.RemoveField(model_name="rule", name="ai_instruction"),
        migrations.RemoveField(model_name="rule", name="tag"),
        migrations.RemoveField(model_name="rule", name="handoff"),
    ]
