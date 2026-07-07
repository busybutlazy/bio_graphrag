from fastapi import APIRouter

from app.eval import runner

router = APIRouter(prefix="/admin")


@router.get("/evaluation/latest")
async def latest_evaluation() -> dict:
    """Run the golden-question evaluation live and return the report.

    Cheap on the sample corpus (~1s); persist=False so dashboard views don't
    spam evaluation_runs. `make eval` remains the persisted / CI-gating path.
    """
    return await runner.run_evaluation(persist=False)
