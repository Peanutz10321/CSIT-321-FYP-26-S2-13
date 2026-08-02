"""Optional organisation ("group") on a user account, and the directory built on it.

Registration may carry a group; organizers and admins can then list the groups that
have members and pull one group's active voters to seed an election's eligible-voter
list. Everything here goes through the public routes against the real test database.
"""

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models.user import User, UserRole, UserStatus
from tests.factories import provision_from_payload


client = TestClient(app)

AUTH_BASE = "/auth"
USER_BASE = "/users"


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def register(role: str = "voter", group: str | None = None) -> dict:
    suffix = uuid4().hex[:8]

    payload = {
        "role": role,
        "username": f"{role}_{suffix}",
        "full_name": f"Test {role.title()}",
        "email": f"{role}_{suffix}@test.com",
        "password": "testing123",
    }
    if group is not None:
        payload["group"] = group

    response = client.post(f"{AUTH_BASE}/register", json=payload)
    assert response.status_code in (200, 201), response.text

    return {**payload, **response.json()}


def login(email: str, password: str = "testing123") -> str:
    response = client.post(
        f"{AUTH_BASE}/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def stored_group(email: str) -> str | None:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        assert user is not None
        return user.group
    finally:
        db.close()


def set_status(email: str, status: UserStatus) -> None:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        assert user is not None
        user.status = status
        db.commit()
    finally:
        db.close()


@pytest.fixture
def organizer_token():
    organizer = register("organizer")
    return login(organizer["email"])


@pytest.fixture
def unique_group():
    return f"Group-{uuid4().hex[:8]}"


class TestRegistrationGroup:
    def test_registration_stores_the_submitted_group(self):
        voter = register("voter", group="Engineering Club")

        assert stored_group(voter["email"]) == "Engineering Club"

    def test_group_is_optional(self):
        voter = register("voter")

        assert stored_group(voter["email"]) is None

    def test_blank_group_is_stored_as_null_not_empty_string(self):
        """Otherwise "" would show up as a selectable organisation."""
        voter = register("voter", group="   ")

        assert stored_group(voter["email"]) is None


class TestGroupDirectory:
    def test_organizer_sees_a_group_that_has_active_voters(self, organizer_token, unique_group):
        register("voter", group=unique_group)

        response = client.get(f"{USER_BASE}/groups", headers=auth_header(organizer_token))

        assert response.status_code == 200, response.text
        assert unique_group in response.json()

    def test_group_is_listed_once_however_many_members(self, organizer_token, unique_group):
        register("voter", group=unique_group)
        register("voter", group=unique_group)

        groups = client.get(f"{USER_BASE}/groups", headers=auth_header(organizer_token)).json()

        assert groups.count(unique_group) == 1

    def test_a_group_with_no_active_voters_is_not_offered(self, organizer_token, unique_group):
        voter = register("voter", group=unique_group)
        set_status(voter["email"], UserStatus.suspended)

        groups = client.get(f"{USER_BASE}/groups", headers=auth_header(organizer_token)).json()

        assert unique_group not in groups

    def test_voters_cannot_browse_the_group_directory(self, unique_group):
        voter = register("voter", group=unique_group)
        token = login(voter["email"])

        response = client.get(f"{USER_BASE}/groups", headers=auth_header(token))

        assert response.status_code == 403

    def test_group_directory_requires_authentication(self):
        assert client.get(f"{USER_BASE}/groups").status_code == 401


class TestGroupMembers:
    def test_organizer_gets_the_external_ids_of_a_groups_active_voters(
        self, organizer_token, unique_group
    ):
        first = register("voter", group=unique_group)
        second = register("voter", group=unique_group)
        register("voter", group=f"Other-{uuid4().hex[:8]}")

        response = client.get(
            f"{USER_BASE}/by-group",
            params={"group_name": unique_group},
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 200, response.text

        external_ids = {member["external_id"] for member in response.json()}
        assert external_ids == {first["external_id"], second["external_id"]}

    def test_only_active_voters_are_returned(self, organizer_token, unique_group):
        active = register("voter", group=unique_group)
        suspended = register("voter", group=unique_group)
        set_status(suspended["email"], UserStatus.suspended)

        members = client.get(
            f"{USER_BASE}/by-group",
            params={"group_name": unique_group},
            headers=auth_header(organizer_token),
        ).json()

        assert [member["external_id"] for member in members] == [active["external_id"]]

    def test_organizers_in_a_group_are_not_returned_as_voters(self, organizer_token, unique_group):
        """The list seeds an election's eligible voters, which only accept voter accounts."""
        organizer_payload = {
            "role": "organizer",
            "username": f"organizer_{uuid4().hex[:8]}",
            "full_name": "Test Organizer",
            "email": f"organizer_{uuid4().hex[:8]}@test.com",
            "password": "testing123",
        }
        provisioned = provision_from_payload(organizer_payload)
        db = SessionLocal()
        try:
            row = db.query(User).filter(User.id == UUID(provisioned["id"])).first()
            row.group = unique_group
            db.commit()
        finally:
            db.close()

        voter = register("voter", group=unique_group)

        members = client.get(
            f"{USER_BASE}/by-group",
            params={"group_name": unique_group},
            headers=auth_header(organizer_token),
        ).json()

        assert [member["external_id"] for member in members] == [voter["external_id"]]

    def test_an_unknown_group_is_an_empty_list_not_a_404(self, organizer_token):
        response = client.get(
            f"{USER_BASE}/by-group",
            params={"group_name": f"NoSuchGroup-{uuid4().hex[:8]}"},
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 200, response.text
        assert response.json() == []

    def test_voters_cannot_read_a_groups_membership(self, unique_group):
        member = register("voter", group=unique_group)
        token = login(member["email"])

        response = client.get(
            f"{USER_BASE}/by-group",
            params={"group_name": unique_group},
            headers=auth_header(token),
        )

        assert response.status_code == 403

    def test_returned_members_are_all_active_voter_accounts(self, organizer_token, unique_group):
        register("voter", group=unique_group)

        members = client.get(
            f"{USER_BASE}/by-group",
            params={"group_name": unique_group},
            headers=auth_header(organizer_token),
        ).json()

        assert members
        for member in members:
            assert member["role"] == UserRole.voter.value
            assert member["status"] == UserStatus.active.value


class TestRegistrationGroupLength:
    """The column is VARCHAR(50), so the schema rejects anything longer.

    Validation lives in the Pydantic model on purpose: PostgreSQL would answer an
    oversized value with StringDataRightTruncation, which surfaces as a 500 rather
    than something a client can act on.
    """

    def test_a_50_character_group_is_accepted_and_stored_whole(self):
        name = "G" * 50

        voter = register("voter", group=name)

        assert stored_group(voter["email"]) == name

    def test_a_51_character_group_is_rejected(self):
        suffix = uuid4().hex[:8]
        response = client.post(
            f"{AUTH_BASE}/register",
            json={
                "role": "voter",
                "username": f"voter_{suffix}",
                "full_name": "Too Long",
                "email": f"voter_{suffix}@test.com",
                "password": "testing123",
                "group": "G" * 51,
            },
        )

        assert response.status_code == 422, response.text
        # The response names the offending field rather than leaking a DB error.
        assert "group" in response.text

    def test_a_rejected_group_creates_no_account(self):
        suffix = uuid4().hex[:8]
        email = f"voter_{suffix}@test.com"

        response = client.post(
            f"{AUTH_BASE}/register",
            json={
                "role": "voter",
                "username": f"voter_{suffix}",
                "full_name": "Too Long",
                "email": email,
                "password": "testing123",
                "group": "G" * 51,
            },
        )
        assert response.status_code == 422

        db = SessionLocal()
        try:
            assert db.query(User).filter(User.email == email).first() is None
        finally:
            db.close()


class TestGroupMembersQueryParameter:
    """The group name travels as a query parameter, not a path segment.

    A path segment cannot carry '/' dependably â€” percent-encoded slashes are
    normalised inconsistently by proxies and ASGI servers â€” and group names are
    organizer-authored free text.
    """

    def test_the_group_name_is_required(self, organizer_token):
        response = client.get(f"{USER_BASE}/by-group", headers=auth_header(organizer_token))

        assert response.status_code == 422, response.text

    def test_an_empty_group_name_is_rejected(self, organizer_token):
        response = client.get(
            f"{USER_BASE}/by-group",
            params={"group_name": ""},
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 422, response.text

    def test_an_oversized_group_name_is_rejected(self, organizer_token):
        response = client.get(
            f"{USER_BASE}/by-group",
            params={"group_name": "G" * 51},
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 422, response.text

    def test_a_50_character_group_name_is_accepted(self, organizer_token):
        name = "G" * 50
        voter = register("voter", group=name)

        response = client.get(
            f"{USER_BASE}/by-group",
            params={"group_name": name},
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 200, response.text
        assert [m["external_id"] for m in response.json()] == [voter["external_id"]]

    @pytest.mark.parametrize(
        "awkward_name",
        [
            "Faculty of Arts / Humanities",   # a slash a path segment could not carry
            "Chess & Go Club",                # ampersand: a query separator if unescaped
            "Engineering Club",               # a plain space
            "å·¥ç¨‹å­¦ä¼š",                          # non-ASCII
            "CafÃ© SociÃ©tÃ©",                   # accented Latin
            "A/B & C Society ç ”ç©¶",            # all of the above at once
        ],
    )
    def test_awkward_group_names_round_trip(self, organizer_token, awkward_name):
        # Namespaced so a parametrised case cannot collide with another's members.
        name = f"{awkward_name} {uuid4().hex[:6]}"
        assert len(name) <= 50
        voter = register("voter", group=name)

        response = client.get(
            f"{USER_BASE}/by-group",
            params={"group_name": name},
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 200, response.text
        assert [m["external_id"] for m in response.json()] == [voter["external_id"]]

    def test_such_a_group_is_also_listed_in_the_directory(self, organizer_token):
        name = f"A/B & C ç ”ç©¶ {uuid4().hex[:6]}"
        register("voter", group=name)

        groups = client.get(f"{USER_BASE}/groups", headers=auth_header(organizer_token)).json()

        assert name in groups

    def test_the_old_path_style_route_is_gone(self, organizer_token, unique_group):
        """The path form must not still be served alongside the query form."""
        register("voter", group=unique_group)

        response = client.get(
            f"{USER_BASE}/by-group/{unique_group}",
            headers=auth_header(organizer_token),
        )

        assert response.status_code == 404, response.text

    def test_authorization_is_checked_for_the_query_form_too(self, unique_group):
        member = register("voter", group=unique_group)
        token = login(member["email"])

        response = client.get(
            f"{USER_BASE}/by-group",
            params={"group_name": unique_group},
            headers=auth_header(token),
        )

        assert response.status_code == 403


class TestAccountGroupVisibility:
    """The group is part of a user record wherever one is read back."""

    def test_register_response_returns_the_group(self):
        voter = register("voter", group="Engineering Club")

        assert voter["group"] == "Engineering Club"

    def test_users_me_returns_the_group_for_a_voter(self):
        voter = register("voter", group="Engineering Club")
        token = login(voter["email"])

        response = client.get(f"{USER_BASE}/me", headers=auth_header(token))

        assert response.status_code == 200, response.text
        assert response.json()["group"] == "Engineering Club"

    def test_users_me_returns_the_group_for_an_organizer(self):
        organizer = register("organizer", group="Faculty Office")
        token = login(organizer["email"])

        response = client.get(f"{USER_BASE}/me", headers=auth_header(token))

        assert response.status_code == 200, response.text
        assert response.json()["group"] == "Faculty Office"

    def test_an_account_without_a_group_reports_null_rather_than_omitting_it(self):
        voter = register("voter")
        token = login(voter["email"])

        body = client.get(f"{USER_BASE}/me", headers=auth_header(token)).json()

        assert "group" in body
        assert body["group"] is None


class TestAccountGroupUpdate:
    """A user may join, change or leave an organisation from their own account."""

    def test_a_voter_can_set_a_group(self):
        voter = register("voter")
        token = login(voter["email"])

        response = client.put(
            f"{USER_BASE}/me",
            json={"group": "Engineering Club"},
            headers=auth_header(token),
        )

        assert response.status_code == 200, response.text
        assert response.json()["group"] == "Engineering Club"
        assert stored_group(voter["email"]) == "Engineering Club"

    def test_an_organizer_can_set_a_group(self):
        organizer = register("organizer")
        token = login(organizer["email"])

        response = client.put(
            f"{USER_BASE}/me",
            json={"group": "Faculty Office"},
            headers=auth_header(token),
        )

        assert response.status_code == 200, response.text
        assert response.json()["group"] == "Faculty Office"

    def test_a_group_can_be_changed(self):
        voter = register("voter", group="Old Club")
        token = login(voter["email"])

        response = client.put(
            f"{USER_BASE}/me",
            json={"group": "New Club"},
            headers=auth_header(token),
        )

        assert response.status_code == 200, response.text
        assert stored_group(voter["email"]) == "New Club"

    def test_a_blank_group_clears_it(self):
        voter = register("voter", group="Engineering Club")
        token = login(voter["email"])

        response = client.put(
            f"{USER_BASE}/me",
            json={"group": "   "},
            headers=auth_header(token),
        )

        assert response.status_code == 200, response.text
        assert response.json()["group"] is None
        # NULL, not "" â€” an empty string would surface as a selectable organisation.
        assert stored_group(voter["email"]) is None

    def test_an_explicit_null_group_clears_it(self):
        voter = register("voter", group="Engineering Club")
        token = login(voter["email"])

        response = client.put(
            f"{USER_BASE}/me",
            json={"group": None},
            headers=auth_header(token),
        )

        assert response.status_code == 200, response.text
        assert stored_group(voter["email"]) is None

    def test_omitting_the_group_leaves_it_untouched(self):
        """Updating only the username must not wipe the organisation."""
        voter = register("voter", group="Engineering Club")
        token = login(voter["email"])

        response = client.put(
            f"{USER_BASE}/me",
            json={"username": f"renamed_{uuid4().hex[:8]}"},
            headers=auth_header(token),
        )

        assert response.status_code == 200, response.text
        assert stored_group(voter["email"]) == "Engineering Club"

    def test_the_group_is_trimmed_on_update(self):
        voter = register("voter")
        token = login(voter["email"])

        client.put(
            f"{USER_BASE}/me",
            json={"group": "  Engineering Club  "},
            headers=auth_header(token),
        )

        assert stored_group(voter["email"]) == "Engineering Club"

    def test_a_50_character_group_is_accepted(self):
        voter = register("voter")
        token = login(voter["email"])
        name = "G" * 50

        response = client.put(
            f"{USER_BASE}/me",
            json={"group": name},
            headers=auth_header(token),
        )

        assert response.status_code == 200, response.text
        assert stored_group(voter["email"]) == name

    def test_a_51_character_group_is_rejected_and_changes_nothing(self):
        voter = register("voter", group="Engineering Club")
        token = login(voter["email"])

        response = client.put(
            f"{USER_BASE}/me",
            json={"group": "G" * 51},
            headers=auth_header(token),
        )

        assert response.status_code == 422, response.text
        assert stored_group(voter["email"]) == "Engineering Club"

    def test_updating_a_group_makes_the_account_selectable_through_the_directory(
        self, organizer_token, unique_group
    ):
        """The whole point of the field: an organizer can then enrol the account."""
        voter = register("voter")
        token = login(voter["email"])

        client.put(
            f"{USER_BASE}/me",
            json={"group": unique_group},
            headers=auth_header(token),
        )

        members = client.get(
            f"{USER_BASE}/by-group",
            params={"group_name": unique_group},
            headers=auth_header(organizer_token),
        ).json()

        assert [m["external_id"] for m in members] == [voter["external_id"]]

    def test_leaving_a_group_removes_the_account_from_the_directory(
        self, organizer_token, unique_group
    ):
        voter = register("voter", group=unique_group)
        token = login(voter["email"])

        client.put(f"{USER_BASE}/me", json={"group": ""}, headers=auth_header(token))

        members = client.get(
            f"{USER_BASE}/by-group",
            params={"group_name": unique_group},
            headers=auth_header(organizer_token),
        ).json()
        assert members == []

        groups = client.get(f"{USER_BASE}/groups", headers=auth_header(organizer_token)).json()
        assert unique_group not in groups


class TestAccountPasswordMinimum:
    """Updating a password obeys the same minimum registration does.

    Without this the registration rule was advisory: an account could be created
    with a compliant password and immediately lowered to a weaker one.
    """

    def test_a_password_shorter_than_the_minimum_is_rejected(self):
        voter = register("voter")
        token = login(voter["email"])

        response = client.put(
            f"{USER_BASE}/me",
            json={"password": "short"},
            headers=auth_header(token),
        )

        assert response.status_code == 422, response.text

    def test_a_rejected_password_leaves_the_old_one_working(self):
        voter = register("voter")
        token = login(voter["email"])

        client.put(
            f"{USER_BASE}/me",
            json={"password": "short"},
            headers=auth_header(token),
        )

        # The original password still logs in, so nothing was half-applied.
        assert login(voter["email"], "testing123")

    def test_the_registration_minimum_is_the_same_rule(self):
        """Both endpoints reject exactly the same too-short value."""
        suffix = uuid4().hex[:8]
        register_response = client.post(
            f"{AUTH_BASE}/register",
            json={
                "role": "voter",
                "username": f"voter_{suffix}",
                "email": f"voter_{suffix}@test.com",
                "password": "short",
            },
        )

        assert register_response.status_code == 422, register_response.text

    def test_an_eight_character_password_is_accepted_and_logs_in(self):
        voter = register("voter")
        token = login(voter["email"])

        response = client.put(
            f"{USER_BASE}/me",
            json={"password": "12345678"},
            headers=auth_header(token),
        )

        assert response.status_code == 200, response.text
        assert login(voter["email"], "12345678")

    def test_a_seven_character_password_is_rejected(self):
        voter = register("voter")
        token = login(voter["email"])

        response = client.put(
            f"{USER_BASE}/me",
            json={"password": "1234567"},
            headers=auth_header(token),
        )

        assert response.status_code == 422, response.text

    def test_omitting_the_password_still_keeps_the_current_one(self):
        voter = register("voter")
        token = login(voter["email"])

        response = client.put(
            f"{USER_BASE}/me",
            json={"username": f"renamed_{uuid4().hex[:8]}"},
            headers=auth_header(token),
        )

        assert response.status_code == 200, response.text
        assert login(voter["email"], "testing123")
