from fastapi import APIRouter, HTTPException
from server.models.navigation import NavigationEntry, NavigationRepository


def navigation_router(db, run_blocking):
    router = APIRouter(prefix='/api/navigation', tags=['navigation'])
    repository = NavigationRepository(db)

    async def run(method, *args):
        try:
            return await run_blocking(method, *args)
        except KeyError as exc:
            raise HTTPException(404, '导航项目不存在') from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(503, '数据库尚未就绪') from exc

    @router.get('')
    async def list_entries():
        return {'entries': await run(repository.list)}

    @router.post('')
    async def save_entry(entry: NavigationEntry):
        return await run(repository.save, entry)

    @router.delete('/{entry_id}')
    async def delete_entry(entry_id: str):
        await run(repository.delete, entry_id)
        return {'ok': True}

    return router
