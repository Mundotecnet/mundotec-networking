from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/projects")
def projects_placeholder():
    return JSONResponse(
        status_code=501,
        content={"detail": "Módulo Proyectos en desarrollo — disponible próximamente"},
    )
