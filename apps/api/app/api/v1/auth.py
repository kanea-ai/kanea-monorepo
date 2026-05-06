from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import AuthServiceDep
from app.application.auth.schemas import (
    AgentTokenRequest,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
)
from app.domain.exceptions import AuthenticationError, EmailAlreadyExistsError

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, service: AuthServiceDep) -> TokenResponse:
    try:
        return await service.register(payload)
    except EmailAlreadyExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def login(payload: LoginRequest, service: AuthServiceDep) -> TokenResponse:
    try:
        return await service.login(payload)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


@router.post("/agent-token", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def agent_token(payload: AgentTokenRequest, service: AuthServiceDep) -> TokenResponse:
    try:
        return await service.issue_agent_token(payload)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
