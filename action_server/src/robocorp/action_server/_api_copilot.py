import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Dict, List, Optional

import fastapi
from fastapi.params import Param
from fastapi.routing import APIRouter
from starlette.responses import FileResponse

from robocorp.action_server._models import Run

log = logging.getLogger(__name__)
copilot_api_router = APIRouter(prefix="/copilot")


@copilot_api_router.get("/manifest.json", response_model=dict)
def get_copilot_manifest():
    return {
        "id": "https://botframework.com/schemas/manifest",
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "id": "get_current_date",
            "msaAppId": "<Your-Microsoft-App-ID>",
            "endpoint": "https://eighty-six-tall-rabbits.robocorp.link/api/actions/actions-robo/get-current-date/run",
            "iconUrl": "<URL-of-Icon-for-Your-Action>",
            "authenticationConnections": [],
        },
        "actions": [
            {
                "id": "get_current_date",
                "definition": {}
            }
        ],
    }
