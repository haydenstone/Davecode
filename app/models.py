"""AENIMUS API models v0.1.0."""
from typing import Any, Literal
from pydantic import BaseModel, Field


class Voice(BaseModel):
    enabled: bool = False
    engine: str = "browser"
    voice_id: str = "default"
    rate: float = Field(1, ge=.5, le=2)
    pitch: float = Field(1, ge=0, le=2)
    style: str = "calm"


class MemoryPolicy(BaseModel):
    mode: Literal["private", "shared", "hybrid"] = "hybrid"
    retain_turns: int = Field(24, ge=0, le=500)
    summarize: bool = True


class Agent(BaseModel):
    id: str
    name: str
    role: Literal["planner", "executor", "reviewer", "specialist"] = "specialist"
    persona: str = ""
    persona_layers: list[str] = Field(default_factory=list)
    mission: str = ""
    provider: str = "ollama"
    model: str = "llama3.2"
    temperature: float = Field(.4, ge=0, le=2)
    context_window: int = Field(8192, ge=512, le=1_000_000)
    tuning: dict[str, Any] = Field(default_factory=dict)
    tools: list[str] = Field(default_factory=lambda: ["read_file"])
    permissions: dict[str, bool] = Field(default_factory=lambda: {"delegate": False, "write": False, "terminal": False})
    memory: MemoryPolicy = Field(default_factory=MemoryPolicy)
    color: str = "#9bf00b"
    avatar: str = "AI"
    voice: Voice = Field(default_factory=Voice)


class Provider(BaseModel):
    id: str
    label: str
    base_url: str
    api_key_env: str | None = None
    enabled: bool = True


class SessionCreate(BaseModel):
    title: str = "Untitled operation"
    agent_ids: list[str] = Field(default_factory=list)
    orchestration: Literal["direct", "pipeline", "swarm"] = "pipeline"

class Swarm(BaseModel):
    id: str
    name: str
    description: str = ""
    agent_ids: list[str]
    orchestration: Literal["direct", "pipeline", "swarm"] = "pipeline"
    head_agent_id: str | None = None


class ChatRequest(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)
    agent_id: str | None = None
    success_criteria: str = "Fulfill the requested outcome accurately and completely."
    max_rounds: int = Field(2, ge=1, le=8)


class FileRequest(BaseModel):
    path: str


class WriteRequest(FileRequest):
    content: str
    approval_id: str | None = None


class TerminalRequest(BaseModel):
    argv: list[str] = Field(min_length=1, max_length=64)
    cwd: str = "."
    approval_id: str | None = None

class DiagnosticRequest(BaseModel):
    path: str = "."
    mode: Literal["lint", "test", "debug"] = "lint"


class ApprovalDecision(BaseModel):
    approved: bool

class MaintenanceRequest(BaseModel):
    name: str | None = None
    scope: Literal["history", "memory", "all"] = "history"
    approval_id: str | None = None
