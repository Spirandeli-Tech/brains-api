"""HTTP surface for the Devocionais listing — a single read-only endpoint that
merges the blog frontmatter, the Telegram ledger, and the narrated-video
meta.yaml files. No runner endpoint: no skill needs to read this list today."""
from fastapi import APIRouter, Depends

from app.core.auth import get_current_user
from app.models.user import User
from app.schemas.devocional import DevocionalRead
from app.services import devocional_service as svc

router = APIRouter(prefix="/devocionais", tags=["devocionais"])


@router.get("", response_model=list[DevocionalRead])
def list_devocionais(current_user: User = Depends(get_current_user)):
    return svc.list_devocionais()
