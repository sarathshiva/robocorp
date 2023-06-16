"""Module with Planhat function keywords"""
import requests
import sys
import logging
from typing import Any, Dict, List, Union, Optional
from enum import Enum

from tenacity import Retrying, stop_after_attempt, wait_fixed, RetryError

from robocorp.vault import get_secret

from ._enums import (
    PlanhatIdTypes,
    PlanhatObjectTypes,
)

LOGGER = logging.getLogger(__name__)
BASE_PH_URL = requests.models.parse_url("https://api-us3.planhat.com")


class Planhat:
    """Class with Planhat function keywords"""

    def __init__(self) -> None:
        self.logger = LOGGER
        self.cached_credentials = None

        # Set up console logger, will only log INFO and above to console
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)

    def _build_planhat_url(
        self, object_type: PlanhatObjectTypes, id: Optional[str] = None
    ) -> str:
        """Builds the Planhat URL for the given object type and ID.

        :param object_type: The Planhat object type.
        :param id: The Planhat object ID.
        :returns: The Planhat URL for the given object type and ID.
        """
        if id:
            return f"{BASE_PH_URL}/{object_type.value}/{id}"
        else:
            return f"{BASE_PH_URL}/{object_type.value}"

    def set_planhat_company_id_to_hubspot_object(
        self,
        hubspot_objects: List,
        planhat_companies: List[Dict],
        hubspot_associations: Dict,
    ) -> List[Dict]:
        """Sets the ``_id`` property in the Hubspot objects' ``property``
        attribute using the provied list of association objects and Planhat
        Company objects. Returns the updated Hubspot objects as a list.

        :param hubspot_objects: The list of associated Hubspot Objects
        :param planhat_companies: The list of Planhat Company objects from Planhat
         to which the hubspot objects should be associated.
        :param hubspot_associations: The association objects from Hubspot. They should be
         in dictionary form where the key is the object ID and the value is a list of
         associations to the target objects.
        """
        # A dictionary with Hubspot Organization ID as keys and Hubspot
        # Company IDs as values.
        hs_obj_ids_to_hs_comp_ids = {
            a.id: c for (c, ascs) in hubspot_associations.items() for a in ascs
        }
        # A dictionary with Source IDs per Planhat as keys and Planhat
        # Company IDs as values if and only if that company has a Source
        # ID defined.
        hs_comp_id_to_ph_comp_id = {
            p.get("sourceId"): p.get("_id")
            for p in planhat_companies
            if p.get("sourceId")
        }

        for obj in hubspot_objects:
            obj.properties["_id"] = hs_comp_id_to_ph_comp_id[
                hs_obj_ids_to_hs_comp_ids[obj.id]
            ]

        self.logger.log(logging.DEBUG, "Updated Hubspot objects: {}", hubspot_objects)

        return hubspot_objects

    def find_planhat_object_associated_with_hubspot_object(
        self, planhat_objects: List[Dict], hubspot_object: Any, all: bool = False
    ) -> Union[Dict, List]:
        """Looks through the provided list of Planhat objects and returns
        the Planhat object whose ``sourceId` matches the provided Hubspot
        object. If there are multiple matches, returns the first one by
        default. Returns a list if the parameter ``all`` is set to ``True``

        :param planhat_objects: A list of Planhat objects as dictionaries.
        :param hubspot_objects: A Hubspot object.
        :param all: Default ``False``. Return all matched Planhat objects.
        :returns: A dictionary representing the found Planhat Object.
        """
        found_ph_objs = [
            obj for obj in planhat_objects if obj.get("sourceId") == hubspot_object.id
        ]
        if found_ph_objs:
            self.logger.log(
                logging.INFO, f"Found {len(found_ph_objs)} object(s): {found_ph_objs!r}"
            )
            if all:
                return found_ph_objs
            else:
                return found_ph_objs[0]
        else:
            self.logger.log(logging.INFO, "No matching object found.")
            return {}

    def create_planhat_id_parameter(
        self, id: str, id_type: Optional[Union[PlanhatIdTypes, str]] = None
    ) -> str:
        """Creates the ID paramater for a query based on the provided
        `id` and `id_type`.
        """
        if id_type is not None:
            if isinstance(id_type, str):
                try:
                    member = getattr(PlanhatIdTypes, str(id_type).upper())
                except AttributeError:
                    raise AttributeError(
                        f"Invalid Planhat ID type: {id_type}, must be one of {PlanhatIdTypes.__members__.keys()}"
                    )
                id_type = member()
            out = f"{id_type.value}{id}"
        else:
            out = str(id)
        self.logger.log(logging.DEBUG, f"Created ID parameter: {out}")
        return out

    def bulk_upsert_planhat_objects(
        self, object_type: PlanhatObjectTypes, payload: List[Dict]
    ):
        if len(payload) == 0:
            self.logger.warning("Payload is empty and will not be sent to Planhat.")
            return {}
        elif len(payload) > 5000:
            batched_responses = []
            for counter in range(0, 1000):
                bottom = counter * 5000
                top = bottom + 5000
                response = self.bulk_upsert_one_planhat_object_batch(
                    object_type, payload[bottom:top]
                )
                batched_responses.append(response)
            return batched_responses
        else:
            response = self.bulk_upsert_one_planhat_object_batch(object_type, payload)
            return response

    def bulk_upsert_one_planhat_object_batch(
        self, object_type: PlanhatObjectTypes, payload: Dict
    ):
        headers = self.create_planhat_headers()
        response = requests.put(
            url=self._build_planhat_url(object_type), headers=headers, json=payload
        )
        return response.json()

    def create_planhat_headers(self):
        """Creates the appropriate headers for a Planhat request, including
        the authorization header.
        """
        self.cached_credentials = None
        if self.cached_credentials is None:
            self.cached_credentials = get_secret("planhat_api")
        output = {
            "Authorization": f"Bearer {self.cached_credentials['api_key']}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        return output

    def get_planhat_object(
        self,
        object_type: PlanhatObjectTypes,
        ids: Optional[List] = None,
        properties: Optional[List] = None,
    ) -> List[Dict]:
        """Primarily private function used to simplify other function calls. This will get a list
        of objects from an PH endpoint that can accept a list of company IDs (via `ids`) and `properties` as
        parameters. The type of object requested must be a valid planhat object type. See
        specific object-related keywords for full documentation of the API.
        """
        if object_type not in PlanhatObjectTypes:
            raise ValueError(
                f"{object_type} is not a valid Planhat object type. Valid types are {PlanhatObjectTypes}"
            )
        if ids is not None and not isinstance(ids, list):
            raise ValueError(f"ids must be a list. Received {ids}")
        if properties is not None and not isinstance(properties, list):
            raise ValueError(f"properties must be a list. Received {properties}")

        self.logger.info(
            f"Getting '{object_type}' with ids '{ids}' and properties '{properties}'"
        )
        if object_type == PlanhatObjectTypes.COMPANIES:
            limit = 5000
        else:
            limit = 2000
        headers = self.create_planhat_headers()
        ids = ",".join(ids) if ids else None
        properties = ",".join(properties) if properties else None
        params = {"limit": limit}
        if ids is not None:
            params["companyId"] = ids
        if properties is not None:
            params["select"] = properties
        full_response = []
        for counter in range(1000):
            self.logger.info(f"Getting {object_type} batch {counter}")
            bottom = counter * limit
            params["offset"] = bottom
            self.logger.debug(f"Full params to be sent: {params}")
            try:
                for attempt in Retrying(stop=stop_after_attempt(3), wait=wait_fixed(2)):
                    with attempt:
                        current_response = requests.get(
                            url=self._build_planhat_url(object_type),
                            headers=headers,
                            params=params,
                        )
                        current_response.raise_for_status()
            except RetryError:
                pass
            if current_response.status_code == 200:
                response_length = len(current_response.json())
                self.logger.debug(f"Response received: {current_response.status_code}")
                full_response.extend(current_response.json())
                if response_length < limit or response_length == 0:
                    break
            else:
                self.logger.error(
                    f"Error getting {object_type} with params {params}. Response code: {current_response.status_code}"
                )
                break
        self.logger.debug(full_response)
        return full_response

    def get_planhat_object_by_id(
        self,
        object_type: PlanhatObjectTypes,
        id: Optional[str] = None,
        id_type: Optional[Union[PlanhatIdTypes, str]] = None,
    ) -> Union[Dict, requests.Response, None]:
        """Gets a planhat object of `object_type` using
        the provided `id`. You can provide alternate ids via the `id_type`. If no object is found
        or a network error occurs, the `None` object is returned.
        """
        if id is None:
            self.logger.warning("No ID provided, returning None.")
            return None
        id_to_use = self.create_planhat_id_parameter(id, id_type)
        headers = self.create_planhat_headers()
        response = requests.get(
            url=self._build_planhat_url(object_type, id_to_use), headers=headers
        )
        if response.status_code > 200:
            self.logger.warning(f"NetworkError: {response.reason}")
            return None
        else:
            try:
                response = response.json()
            except:
                self.logger.warning("Could not replace response object with JSON.")
            return response

    def update_planhat_object(
        self,
        object_type: PlanhatObjectTypes,
        id: str,
        payload: Dict,
        id_type: Optional[PlanhatIdTypes] = None,
    ) -> Union[Dict, requests.Response, None]:
        """Updates a planhat object of `object_type` using
        the provided `id`. You can provide alternate ids via the `id_type`. If no object is found
        or a network error occurs, the `None` object is returned.
        """
        if id is None:
            self.logger.warning("No ID provided, returning None.")
            return None
        id_to_use = self.create_planhat_id_parameter(id, id_type)
        headers = self.create_planhat_headers()
        response = requests.put(
            url=self._build_planhat_url(object_type, id_to_use),
            headers=headers,
            json=payload,
        )
        try:
            response.raise_for_status()
            response = response.json()
        except requests.HTTPError:
            self.logger.warning(f"NetworkError: {response.reason}")
            return None
        except Exception:
            self.logger.warning("Could not replace response object with JSON.")
        return response

    def delete_planhat_object(
        self, object_type: PlanhatObjectTypes, id: str, ignore_errors: bool = False
    ):
        headers = self.create_planhat_headers()
        response = requests.delete(
            url=self._build_planhat_url(object_type, id), headers=headers
        )
        if not ignore_errors:
            response.raise_for_status()
        try:
            response = response.json()
        except:
            self.logger.warning("Could not replace response object with JSON.")
        return response

    def list_companies(
        self,
        status: Optional[str] = None,
        ids: Optional[List] = None,
        properties: Optional[List] = None,
    ):
        """Lists all companies in Planhat. By default, this function uses the "lean" API, which
        produces a list of dictionaries only containing the company name, Planhat ID, source ID,
        and external ID. You can filter by status. If you want the full properties of companies,
        you can provide anything to the `ids` or `properties` parameters and the main API will be
        used. If you want all companies and all properties, give either parameter the string
        `ALL`. If you provide a list of `properties` only they and `_id` will be returned, if a
        property does not exist, it will be ignored.

        If the full API is used, returns a list of dictionaries where the keys of each dictionary
        include the returned properties. Custom properties will be all attached as a dictionary
        to the key `custom`. Usage information will be attached to the key `usage`. The default
        keys include:

            - `_id`
            - `sourceId`
            - `externalId`
            - `slug`
            - `name`
            - `description`
            - `website`
            - `domains` (this is a list of domains)
            - `phonePrimary`
            - `custom` (dictionary of all custom properties)
            - `web`
            - `status`
            - `phonePrimaryRaw`
            - `sunits`
            - `createDate`
            - `createdAt`
            - `updatedAt`
            - `customerFrom`
            - `headId`
            - `lastRenewal`
            - `lastUpdated`
            - `mr`
            - `mrTotal`
            - `mrr`
            - `mrrTotal`
            - `nrr30`
            - `nrrTotal`
            - `products`
            - `renewalMrr`
            - `lastTouch`
            - `lastTouchType`
            - `lastTouchByType`
            - `h`
            - `usage`
            - `hDiff`
            - `hDiffDate`
            - `hProfile`
            - `beatDate`
            - `lastActive`
            - `owner`
            - `customerTo`
            - `renewalDate`
            - `renewalDaysFromNow`
            - `phase`
            - `phaseSince`
            - `coOwner`
            - `nextTouch`

        Caution should be exercised when referencing keys as there is a chance such keys may
        not exist depending on how the API responded.
        """
        if ids is None and properties is None:
            headers = self.create_planhat_headers()
            params = {"status": status} if status is not None else {}
            response = requests.get(
                f"{BASE_PH_URL}/leancompanies", params=params, headers=headers
            )
            return response.json()
        else:
            if "ALL" in ids:
                ids = None
            if "ALL" in properties:
                properties = None
            full_response = self.get_planhat_object(
                PlanhatObjectTypes.COMPANY, ids=ids, properties=properties
            )
            return full_response

    def match_planhat_companies_via_domain(self, ph_companies, domain):
        matching_ph_companies = [
            c
            for c in ph_companies
            if c.get("website") == domain
            or domain in c.get("domains", [])
            or c.get("web") == domain
        ]
        self.logger.debug(matching_ph_companies)
        return matching_ph_companies
