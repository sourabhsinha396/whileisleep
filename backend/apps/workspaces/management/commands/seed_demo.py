"""Creates a demo owner and two workspaces to try whileisleep locally. Safe to run again.

    docker compose exec -T web python manage.py seed_demo

Login: DEMO_EMAIL / DEMO_PASSWORD from .env. Add an AI key and pick the model in Settings, AI
model. The first workspace's tools call a site's public API (a dev server on the
host); the second is a plain knowledge-base-only shop.
"""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.agent.models import Playbook, Rule, Tool
from apps.knowledge.models import Article
from apps.workspaces.models import Workspace
from apps.workspaces.services import create_workspace

EXAM_API = "http://host.docker.internal:8006"

WORKSPACES = [
    {
        "name": "Acme Exams",
        "website": "http://localhost:3006",
        "color": "#2563eb",
        "greeting": "Hi! Looking for a practice exam? Ask me about any certification.",
        "ai_instructions": (
            "Acme Exams sells practice tests for IT certification exams. When someone asks about an exam, "
            "search the catalog with search_exams before answering, and link the exam page as "
            "/exams/{slug}. If it isn't in the catalog, check exams_in_preparation."
        ),
        "articles": [
            (
                "Refund policy",
                "If you don't pass, ask for a refund within 30 days of your exam date. Send your score report.",
            ),
            (
                "How practice tests work",
                "Each test has timed and practice modes. Practice mode shows explanations after each question.",
            ),
        ],
        "tools": [
            {
                "name": "search_exams",
                "description": (
                    "Searches the catalog of practice exams by exam code or name (e.g. 'AZ-104', 'aws solutions "
                    "architect'). Returns matching exams with code, name, slug, price_cents and discount. Use it "
                    "whenever someone asks whether an exam is available or what it costs."
                ),
                "url": f"{EXAM_API}/api/v1/exams",
                "input_schema": {
                    "type": "object",
                    "properties": {"q": {"type": "string", "description": "Exam code or name."}},
                    "required": ["q"],
                },
            },
            {
                "name": "exams_in_preparation",
                "description": (
                    "Exams that are being prepared but not yet published, for a search that found nothing. "
                    "Use it to tell the visitor an exam is coming soon."
                ),
                "url": f"{EXAM_API}/api/v1/exams/pending",
                "input_schema": {
                    "type": "object",
                    "properties": {"q": {"type": "string", "description": "Exam code or name."}},
                    "required": ["q"],
                },
            },
        ],
        # The "Ask us in chat" button on exams in preparation sends intent exam_request.
        "rules": [
            {
                "name": "Exam requests",
                "conditions": {"all": [{"field": "message.intent", "op": "equals", "value": "exam_request"}]},
                "actions": [
                    {"type": "tag", "value": "exam-request"},
                    {
                        "type": "reply",
                        "text": "Thanks! We'll try to add {message.data.exam_name} within 12 hours, and we'll reply here once it's live.",
                    },
                ],
                "also_when_human": True,
            },
        ],
        "playbooks": [
            {
                "title": "Refund requests",
                "when_to_use": "The visitor asks for a refund or says they failed their exam.",
                "instructions": (
                    "1. Say sorry about the result.\n"
                    "2. Ask for the exam date and a photo of the score report.\n"
                    "3. If the exam was within 30 days, say a teammate will process the refund and call "
                    "handoff_to_human.\n"
                    "4. Otherwise explain kindly that refunds are only within 30 days of the exam."
                ),
            },
        ],
    },
    {
        "name": "Little Fern Coffee",
        "website": "https://littlefern.example.com",
        "color": "#15803d",
        "greeting": "Hi! Questions about beans, brewing or your order?",
        "ai_instructions": "Friendly, brief. We roast in small batches and ship weekly.",
        "articles": [
            (
                "Shipping",
                "We ship to the UK, EU, US and Canada. Orders arrive in **5 to 8 business days**. "
                "Shipping is free on orders over $60.",
            ),
            ("Wholesale", "Cafés can order wholesale from 5 kg a month. Email wholesale@littlefern.example.com."),
            ("Changing your delivery address", "You can change the address until the order ships, usually Thursday."),
        ],
        "tools": [],
        "rules": [],
        "playbooks": [],
    },
]


class Command(BaseCommand):
    help = "Create a demo owner and two workspaces."

    def handle(self, *args, **options):
        email = os.environ.get("DEMO_EMAIL", "").lower()
        password = os.environ.get("DEMO_PASSWORD", "")
        if not email or not password:
            raise CommandError("Set DEMO_EMAIL and DEMO_PASSWORD in .env first.")
        User = get_user_model()
        user, created = User.objects.get_or_create(username=email, defaults={"email": email, "first_name": "Demo"})
        if created:
            user.set_password(password)
            user.save()

        for spec in WORKSPACES:
            spec = dict(spec)
            articles, tools = spec.pop("articles"), spec.pop("tools")
            rules, playbooks = spec.pop("rules"), spec.pop("playbooks")
            workspace = Workspace.objects.filter(name=spec["name"], memberships__user=user).first()
            if workspace is None:
                workspace = create_workspace(user, **spec)
            for title, body in articles:
                Article.objects.get_or_create(workspace=workspace, title=title, defaults={"body": body})
            for rule in rules:
                Rule.objects.update_or_create(workspace=workspace, name=rule["name"], defaults=rule)
            for playbook in playbooks:
                Playbook.objects.update_or_create(workspace=workspace, title=playbook["title"], defaults=playbook)
            for tool in tools:
                Tool.objects.update_or_create(workspace=workspace, name=tool["name"], defaults=tool)
            self.stdout.write(f"{workspace.name}: {workspace.public_key}")
        self.stdout.write(self.style.SUCCESS(f"Log in as {email}."))
