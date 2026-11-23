"""Object factories for tests. Build what a test needs and override only what it checks:

workspace = WorkspaceFactory()
MessageFactory(conversation__workspace=workspace, body="Hi")
"""

import factory
from django.contrib.auth import get_user_model

from apps.accounts.models import AuthToken
from apps.agent.models import Tool
from apps.conversations.models import Conversation, Message, Visitor
from apps.knowledge.models import Article
from apps.workspaces.models import Membership, Organization, Workspace


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = get_user_model()
        skip_postgeneration_save = True

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    username = factory.SelfAttribute("email")
    first_name = factory.Faker("first_name")
    password = factory.PostGenerationMethodCall("set_password", "password123")

    @factory.post_generation
    def save_password(obj, create, extracted, **kwargs):
        if create:
            obj.save()


class AuthTokenFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = AuthToken

    user = factory.SubFactory(UserFactory)


class OrganizationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Organization

    name = factory.Sequence(lambda n: f"Org {n}")
    owner = factory.SubFactory(UserFactory)

    class Params:
        # Has an OpenRouter key and model, so the bot calls the (fake) LLM.
        ready = factory.Trait(openrouter_api_key="sk-or-test-key-1234", llm_model="test/model")


class WorkspaceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Workspace

    organization = factory.SubFactory(OrganizationFactory)
    name = factory.Sequence(lambda n: f"Shop {n}")
    website = factory.LazyAttribute(lambda w: f"https://{w.name.lower().replace(' ', '')}.example.com")


class MembershipFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Membership

    user = factory.SubFactory(UserFactory)
    workspace = factory.SubFactory(WorkspaceFactory)
    role = Membership.Role.OWNER


class VisitorFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Visitor

    workspace = factory.SubFactory(WorkspaceFactory)
    current_url = factory.LazyAttribute(lambda v: f"{v.workspace.website}/pricing")


class ConversationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Conversation

    workspace = factory.SubFactory(WorkspaceFactory)
    visitor = factory.SubFactory(VisitorFactory, workspace=factory.SelfAttribute("..workspace"))


class MessageFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Message

    conversation = factory.SubFactory(ConversationFactory)
    sender = Message.Sender.VISITOR
    body = factory.Faker("sentence")


class ArticleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Article

    workspace = factory.SubFactory(WorkspaceFactory)
    title = factory.Sequence(lambda n: f"Article {n}")
    body = factory.Faker("paragraph")


class ToolFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Tool

    workspace = factory.SubFactory(WorkspaceFactory)
    name = factory.Sequence(lambda n: f"lookup_{n}")
    description = "Looks up products by keyword. Returns name, price and availability."
    url = "https://api.example.com/products"
    input_schema = factory.LazyFunction(
        lambda: {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}
    )
