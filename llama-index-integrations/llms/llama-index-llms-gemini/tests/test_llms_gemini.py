import os

import pytest
from google.ai.generativelanguage_v1beta.types import (
    FunctionCallingConfig,
    ToolConfig,
)
from google.generativeai.types.content_types import FunctionCallingMode
import google.generativeai as genai

from llama_index.core.base.llms.base import BaseLLM
from llama_index.core.base.llms.types import ChatMessage, ImageBlock, MessageRole
from llama_index.core.prompts.base import ChatPromptTemplate
from llama_index.core.tools.function_tool import FunctionTool
from llama_index.llms.gemini import Gemini
from llama_index.llms.gemini.utils import chat_message_to_gemini
from pydantic import BaseModel, Field
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_gemini_context():
    """
    Fixture that provides a context manager for mocking both google.generativeai.get_model
    and google.generativeai.GenerativeModel for Gemini LLM testing.

    Yields:
        MagicMock: A mock that simulates genai.types.Model with the required attributes
                   for Gemini LLM initialization and testing.

    """
    mock_model = MagicMock(spec=genai.types.Model)
    mock_model.supported_generation_methods = ["generateContent"]
    mock_model.output_token_limit = 2048

    with (
        patch("google.generativeai.get_model", return_value=mock_model),
        patch("google.generativeai.GenerativeModel"),
    ):
        yield mock_model


def test_embedding_class() -> None:
    names_of_base_classes = [b.__name__ for b in Gemini.__mro__]
    assert BaseLLM.__name__ in names_of_base_classes


def test_chat_message_to_gemini() -> None:
    msg = ChatMessage("Some content")
    assert chat_message_to_gemini(msg) == {
        "role": MessageRole.USER,
        "parts": [{"text": "Some content"}],
    }

    msg = ChatMessage("Some content")
    msg.blocks.append(ImageBlock(image=b"foo", image_mimetype="image/png"))
    gemini_msg = chat_message_to_gemini(msg)
    assert gemini_msg["role"] == MessageRole.USER
    assert len(gemini_msg["parts"]) == 2


@pytest.mark.skipif(
    os.environ.get("GOOGLE_API_KEY") is None, reason="GOOGLE_API_KEY not set"
)
def test_generate_image_prompt() -> None:
    msg = ChatMessage("Tell me the brand of the car in this image:")
    msg.blocks.append(
        ImageBlock(
            url="https://upload.wikimedia.org/wikipedia/commons/5/52/Ferrari_SP_FFX.jpg",
            image_mimetype="image/jpeg",
        )
    )
    response = Gemini(model="models/gemini-1.5-flash").chat(messages=[msg])
    assert "ferrari" in str(response).lower()


@pytest.mark.skipif(
    os.environ.get("GOOGLE_API_KEY") is None, reason="GOOGLE_API_KEY not set"
)
def test_chat_stream() -> None:
    msg = ChatMessage("List three types of software testing strategies")
    response = list(Gemini(model="models/gemini-1.5-flash").stream_chat(messages=[msg]))
    assert response


@pytest.mark.skipif(
    os.environ.get("GOOGLE_API_KEY") is None, reason="GOOGLE_API_KEY not set"
)
def test_chat_with_tools() -> None:
    def add(a: int, b: int) -> int:
        """Add two integers and returns the result integer."""
        return a + b

    add_tool = FunctionTool.from_defaults(fn=add)
    msg = ChatMessage("What is the result of adding 2 and 3?")
    model = Gemini(model="models/gemini-1.5-flash")
    response = model.chat_with_tools(
        user_msg=msg,
        tools=[add_tool],
        tool_config=ToolConfig(
            function_calling_config=FunctionCallingConfig(
                mode=FunctionCallingConfig.Mode.ANY
            )
        ),
    )

    tool_calls = model.get_tool_calls_from_response(response)
    assert len(tool_calls) == 1
    assert tool_calls[0].tool_name == "add"
    assert tool_calls[0].tool_kwargs == {"a": 2, "b": 3}

    assert len(response.additional_kwargs["tool_calls"]) >= 1


@pytest.mark.skipif(
    os.environ.get("GOOGLE_API_KEY") is None, reason="GOOGLE_API_KEY not set"
)
def test_structured_llm() -> None:
    class Test(BaseModel):
        test: str

    gemini_flash = Gemini(
        model="models/gemini-2.0-flash-001",
        api_key=os.environ["GOOGLE_API_KEY"],
        additional_kwargs={"seed": 4242},
    )

    chat_prompt = ChatPromptTemplate(message_templates=[ChatMessage(content="test")])
    direct_prediction_response = gemini_flash.structured_predict(
        output_cls=Test, prompt=chat_prompt
    )
    assert direct_prediction_response.test is not None
    structured_llm_response = gemini_flash.as_structured_llm(Test).complete("test")
    assert structured_llm_response.raw.test is not None


@pytest.mark.skipif(
    os.environ.get("GOOGLE_API_KEY") is None, reason="GOOGLE_API_KEY not set"
)
def test_is_function_calling_model() -> None:
    assert Gemini(
        model="models/gemini-2.0-flash-001"
    ).metadata.is_function_calling_model

    # this model is the only one that does not support function calling
    assert not Gemini(
        model="models/gemini-2.0-flash-thinking-exp-01-21"
    ).metadata.is_function_calling_model

    # in case of un-released models it should be possible to override the
    # capabilities of the current model
    manual_override = Gemini(model="models/gemini-2.0-flash-001")
    assert manual_override.metadata.is_function_calling_model
    manual_override._is_function_call_model = False
    assert not manual_override._is_function_call_model
    assert not manual_override.metadata.is_function_calling_model


@pytest.mark.skipif(
    os.environ.get("GOOGLE_API_KEY") is None, reason="GOOGLE_API_KEY not set"
)
def test_structure_gen_without_function_call() -> None:
    class Test(BaseModel):
        test: str

    gemini_flash = Gemini(
        model="models/gemini-2.0-flash-001",
        api_key=os.environ["GOOGLE_API_KEY"],
    )
    gemini_flash._is_function_call_model = False
    output = gemini_flash.as_structured_llm(Test).complete("test")
    assert output.raw.test


@pytest.mark.skipif(
    os.environ.get("GOOGLE_API_KEY") is None, reason="GOOGLE_API_KEY not set"
)
@pytest.mark.skip(reason="Invalid schema, to be checked")
def test_function_call_deeply_nested_structured_generation() -> None:
    class Column(BaseModel):
        name: str = Field(description="Column field")
        data_type: str = Field(description="Data type field")

    class Table(BaseModel):
        name: str = Field(description="Table name field")
        columns: list[Column] = Field(description="List of random Column objects")

    class Schema(BaseModel):
        schema_name: str = Field(description="Schema name")
        columns: list[Table] = Field(description="List of random Table objects")

    prompt = ChatPromptTemplate.from_messages(
        [ChatMessage(role="user", content="Generate a simple database structure")]
    )

    gemini_flash = Gemini(
        model="models/gemini-2.0-flash-001",
        api_key=os.environ["GOOGLE_API_KEY"],
    )
    prompt = ChatPromptTemplate.from_messages(
        [ChatMessage(role="user", content="Generate a simple database structure")]
    )

    gemini_flash._is_function_call_model = (
        True  # this is the default, but let's be explicit
    )
    schema = gemini_flash.structured_predict(output_cls=Schema, prompt=prompt)
    assert schema.columns
    assert schema.columns[0].columns
    assert schema.columns[0].columns[0].name


# this is the same test as above, but with function call disabled
@pytest.mark.skipif(
    os.environ.get("GOOGLE_API_KEY") is None, reason="GOOGLE_API_KEY not set"
)
def test_deeply_nested_structured_generation() -> None:
    class Column(BaseModel):
        name: str = Field(description="Column field")
        data_type: str = Field(description="Data type field")

    class Table(BaseModel):
        name: str = Field(description="Table name field")
        columns: list[Column] = Field(description="List of random Column objects")

    class Schema(BaseModel):
        schema_name: str = Field(description="Schema name")
        columns: list[Table] = Field(description="List of random Table objects")

    prompt = ChatPromptTemplate.from_messages(
        [ChatMessage(role="user", content="Generate a simple database structure")]
    )

    gemini_flash = Gemini(
        model="models/gemini-2.0-flash-001",
        api_key=os.environ["GOOGLE_API_KEY"],
    )
    prompt = ChatPromptTemplate.from_messages(
        [ChatMessage(role="user", content="Generate a simple database structure")]
    )
    gemini_flash._is_function_call_model = False
    schema = gemini_flash.structured_predict(output_cls=Schema, prompt=prompt)
    assert schema.columns
    assert schema.columns[0].columns
    assert schema.columns[0].columns[0].name


@pytest.mark.skipif(
    os.environ.get("GOOGLE_API_KEY") is None, reason="GOOGLE_API_KEY not set"
)
def test_stream_complete_text_and_delta() -> None:
    gemini = Gemini(model="models/gemini-1.5-flash")
    prompt = "List three types of software testing strategies in a few words each."
    responses = list(gemini.stream_complete(prompt=prompt))
    assert len(responses) >= 2  # Ensure multiple chunks

    accumulated_text = ""
    for i, response in enumerate(responses):
        assert response.delta  # Delta should be non-empty
        accumulated_text += response.delta
        assert response.text == accumulated_text  # Text should accumulate


# Define a reusable tool for testing
def search(query: str) -> str:
    """Search for information about a query."""
    return f"Results for {query}"


search_tool = FunctionTool.from_defaults(
    fn=search, name="search_tool", description="A tool for searching information"
)


def test_to_function_calling_config(mock_gemini_context: MagicMock):
    llm = Gemini(model="models/gemini-1.5-flash", api_key="fake_key")

    # Test with tool_required=True
    config = llm._to_function_calling_config(tool_required=True, tool_choice=None)
    assert config["mode"] == FunctionCallingMode.ANY

    # Test with tool_required=False
    config = llm._to_function_calling_config(tool_required=False, tool_choice=None)
    assert config["mode"] == FunctionCallingMode.AUTO

    # Test with tool_choice="any"
    config = llm._to_function_calling_config(tool_required=False, tool_choice="any")
    assert config["mode"] == FunctionCallingMode.ANY

    # Test with tool_choice="none"
    config = llm._to_function_calling_config(tool_required=True, tool_choice="none")
    assert config["mode"] == FunctionCallingMode.NONE


def test_prepare_chat_with_tools_tool_required(mock_gemini_context: MagicMock):
    """Test that tool_required=True correctly sets FunctionCallingMode.ANY in the request."""
    llm = Gemini(model="models/gemini-1.5-flash", api_key="fake_key")

    # Test with tool_required=True
    result = llm._prepare_chat_with_tools(tools=[search_tool], tool_required=True)

    assert "tool_config" in result
    assert "function_calling_config" in result["tool_config"]
    assert (
        result["tool_config"]["function_calling_config"]["mode"]
        == FunctionCallingMode.ANY
    )
    assert len(result["tools"]["function_declarations"]) == 1
    assert result["tools"]["function_declarations"][0].name == "search_tool"


def test_prepare_chat_with_tools_tool_not_required(mock_gemini_context: MagicMock):
    llm = Gemini(model="models/gemini-1.5-flash", api_key="fake_key")

    # Test with tool_required=False (default)
    result = llm._prepare_chat_with_tools(
        tools=[search_tool],
    )

    assert "tool_config" in result
    assert "function_calling_config" in result["tool_config"]
    assert (
        result["tool_config"]["function_calling_config"]["mode"]
        == FunctionCallingMode.AUTO
    )
    assert len(result["tools"]["function_declarations"]) == 1
    assert result["tools"]["function_declarations"][0].name == "search_tool"
