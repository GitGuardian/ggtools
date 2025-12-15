#!/usr/bin/env -S uv run --quiet --script
# /// script
# dependencies = [
#   "requests>=2.32.5",
#   "dotenv>=0.9.9",
# ]
# ///
import json
import logging
import requests
import time
import pathlib
import os
from dotenv import load_dotenv
load_dotenv()

# insert the token of the old instance that you would like to migrate from
old_token_instance = os.environ.get("old_token_instance")

# insert the token of the new instance that you would like to migrate to
new_token_instance = os.environ.get("new_token_instance")

# insert the url of the old instance that you would like to migrate from
old_base_api_url = "https://api.gitguardian.com"

# insert the url of the new instance that you would like to migrate to
new_base_api_url = "https://api.gitguardian.com"

# object to save all incident data on the old instance
all_old_incidents = []

# object to save all incident data on the new instance
all_new_incidents = []

# endpoint url used to retrieve incidents
old_endpoint_url = old_base_api_url + "/v1/incidents/secrets"
new_endpoint_url = new_base_api_url + "/v1/incidents/secrets"

# pointed at your internral ca-certificates
import ssl
os.environ["REQUESTS_CA_BUNDLE"] = ssl.get_default_verify_paths().cafile

# initialize logging library
logging.basicConfig(level=logging.DEBUG)

def backoff(func):
    def wrapper(*args, **kwargs):
        wait_time = 1
        wait_status_codes = (None, 429)
        status_code = None
        response = None
        while status_code in wait_status_codes:
            response = func(*args, **kwargs)
            status_code = response.status_code
            if status_code in wait_status_codes:
                logging.error(f"Caught {status_code} sleeping for {wait_time}")
                time.sleep(wait_time)
                wait_time = wait_time * 1.2
        return response
    return wrapper

# method used to retrieve all the incidents on the old instance
all_old_incidents_path = pathlib.Path(__file__).parent.joinpath(".cache", "old_incidents.json")
if all_old_incidents_path.exists():
    all_old_incidents.extend(json.loads(all_old_incidents_path.read_text()))
else:
    while True:
        response = backoff(requests.get)(old_endpoint_url, headers={"Authorization": f"Token {old_token_instance}"})
        assert response.status_code == 200
        all_old_incidents += response.json()

        if "next" not in response.links:
            break

        old_endpoint_url = response.links["next"]["url"]
    all_old_incidents_path.parent.mkdir(parents=True, exist_ok=True)
    all_old_incidents_path.write_text(json.dumps(all_old_incidents))
print("old incidents have been retrieved")


# method used to retrieve all incidents on the new instance
all_new_incidents_path = pathlib.Path(__file__).parent.joinpath(".cache", "new_incidents.json")
if all_new_incidents_path.exists():
    all_new_incidents.extend(json.loads(all_new_incidents_path.read_text()))
else:
    while True:
        response = backoff(requests.get)(new_endpoint_url, headers={"Authorization": f"Token {new_token_instance}"})
        assert response.status_code == 200
        all_new_incidents += response.json()

        if "next" not in response.links:
            break

        new_endpoint_url = response.links["next"]["url"]
    all_new_incidents_path.parent.mkdir(parents=True, exist_ok=True)
    all_new_incidents_path.write_text(json.dumps(all_new_incidents))
print("new incidents have been retrieved")


# notes migration method
def notes_migration(old_secret_id, new_secret_id):

    print("starting notes migration for incident", old_secret_id, "...")
    old_notes_endpoint = old_base_api_url + "/v1/incidents/secrets/"f"{old_secret_id}/notes"
    old_notes = []
    new_notes_endpoint = new_base_api_url + "/v1/incidents/secrets/"f"{new_secret_id}/notes"

    old_notes_path = pathlib.Path(__file__).parent.joinpath(
        ".cache", "old_notes", f"{old_secret_id}.json",
    )
    if old_notes_path.exists():
        old_notes.extend(json.loads(old_notes_path.read_text()))
    else:
        while True:
            note_response = backoff(requests.get)(old_notes_endpoint, headers={"Authorization": f"Token {old_token_instance}"})
            assert note_response.status_code == 200
            old_notes += note_response.json()
            if "next" not in note_response.links:
                break
            old_notes_endpoint = response.links["next"]["url"]
        old_notes_path.parent.mkdir(parents=True, exist_ok=True)
        old_notes_path.write_text(json.dumps(old_notes))
    print("notes retrieved for "f"{old_secret_id}")

    if not old_notes:
        print("no notes on this incident")
        n = 0
    else:
        print(len(old_notes), "note(s) have been found for this incident")

        new_notes_path = pathlib.Path(__file__).parent.joinpath(
            ".cache", "new_notes", f"{new_secret_id}.json",
        )
        if new_notes_path.exists():
            new_notes = json.loads(new_notes_path.read_text())
        else:
            new_incident_note_response = backoff(requests.get)(new_notes_endpoint, headers={"Authorization": f"Token {new_token_instance}"})
            assert new_incident_note_response.status_code == 200
            new_notes = new_incident_note_response.json()
            new_notes_path.parent.mkdir(parents=True, exist_ok=True)
            new_notes_path.write_text(json.dumps(new_notes))
        n = len(new_notes)

        if len(new_notes) == len(old_notes):
            print("Notes for incident", old_secret_id, "have been migrated before, skipping...")

        while n < len(old_notes):
            old_member_path = pathlib.Path(__file__).parent.joinpath(
                ".cache", "old_members", f"{old_notes[n]['member_id']}.json",
            )
            if old_member_path.exists():
                member = json.loads(old_member_path.read_text())
            else:
                member_endpoint = old_base_api_url + "/v1/members/"f"{old_notes[n]['member_id']}"
                member_response = backoff(requests.get)(member_endpoint, headers={"Authorization": f"Token {old_token_instance}"})
                assert member_response.status_code == 200
                member = member_response.json()
                old_member_path.parent.mkdir(parents=True, exist_ok=True)
                old_member_path.write_text(json.dumps(member))
            member_email = member['email']
            print("posting note #", n+1, "...")
            note = f"{member_email}" " left a note on " f"{old_notes[n]['created_at']}" " with the following comment : " f"{old_notes[n]['comment']}"
            print(note)
            post_note(note, new_secret_id)
            n += 1

    print("Notes migration concluded successfully for incident", old_secret_id)

    # Invoke method to post a success message on the new incidents that all notes have been migrated
    notes_migration_success(old_secret_id, new_secret_id)


# method that will post the success message if all notes migrated, this comes after the notes_migration method
def notes_migration_success(old_secret_id, new_secret_id):
    print("posting notes migration success comment on incident " f"{new_secret_id}" " ...")

    counter = check_count(old_secret_id, new_secret_id)

    if counter > 0:
        print("notes migration comment already exists")

    note = "incident " f"{old_secret_id}" " note(s) (if any exist) have been successfully migrated"

    if counter == 0:
        post_note(note, new_secret_id)
        print("notes migration comment has been posted successfully")


# method that will post the note on incidents that have been resolved/ignored
def resolution_note(reason, old_id, date, new_id, member_id):
    res_note = "incident "f"{old_id} has been "
    email = check_member(member_id)
    if reason is True:
        res_note_post = res_note + "resolved and revoked on " f"{date} by {email}"
    if reason is False:
        res_note_post = res_note + "resolved but not revoked on " f"{date} by {email}"
    if reason == "low_risk":
        res_note_post = res_note + "ignored low_risk on " f"{date} by {email}"
    if reason == "false_positive":
        res_note_post = res_note + "ignored false_positive on " f"{date} by {email}"
    if reason == "test_credential":
        res_note_post = res_note + "ignored test_credential on " f"{date} by {email}"
    print(res_note_post)
    # post the resolution note using post_note method
    post_note(res_note_post, new_id)


# method to retrieve member email
def check_member(member_id):
    old_member_path = pathlib.Path(__file__).parent.joinpath(
        ".cache", "old_members", f"{member_id}.json",
    )
    if old_member_path.exists():
        member = json.loads(old_member_path.read_text())
    else:
        member_endpoint = old_base_api_url + "/v1/members/"f"{member_id}"
        member_response = backoff(requests.get)(member_endpoint, headers={"Authorization": f"Token {old_token_instance}"})
        assert response.status_code == 200
        member = member_response.json()
        old_member_path.parent.mkdir(parents=True, exist_ok=True)
        old_member_path.write_text(json.dumps(member))
    member_email = member['email']
    return member_email


# method that will post that all incident details have been successfully migrated
def success_note(old_id, new_id, gitguardian_url, status):

    # check if success note exists , if not then post the success note
    counter = check_count(old_id, new_id)
    note = "incident " f"{old_id}" " migration status successful with the corresponding reference link "f"{gitguardian_url}"

    print(note)
    # post_note(note, id)
    print("incident " f"{old_id}" " migration status successfully posted as a comment on the incident")

    if status != 'TRIGGERED' and counter == 2:
        post_note(note, new_id)
    else:
        if status != 'TRIGGERED' and counter > 2:
            print('note exists')

    if status == 'TRIGGERED' and counter == 1:
        post_note(note, new_id)
    else:
        if status == 'TRIGGERED' and counter == 2:
            print('note exists')


# method used to post notes on incidents
def post_note(note, new_id):
    new_notes_path = pathlib.Path(__file__).parent.joinpath(
        ".cache", "new_notes", f"{new_id}.json",
    )
    new_notes = []
    if new_notes_path.exists():
        new_notes.extend(json.loads(new_notes_path.read_text()))

    # skip if we've already posted this note
    for new_note in new_notes:
        if new_note["comment"] == note:
            return

    note_url = new_base_api_url + "/v1/incidents/secrets/"f"{new_id}""/notes"
    send_note = {"comment": note}
    body = json.dumps(send_note)
    note_response = backoff(requests.post)(note_url, body, headers={"Authorization": f"Token {new_token_instance}", 'Content-Type': 'application/json; charset=UTF-8'})
    response_text = note_response.text
    try:
        assert note_response.status_code == 201
    except:
        logging.error(f"post note {body}: {note_response.status_code}: {note_response.reason}: {response_text}")
        if note_response.status_code == 406:
            errors_path = pathlib.Path(__file__).parent.joinpath(
                ".cache", "errors", "new_notes", f"{new_id}.json",
            )
            errors_path.parent.mkdir(parents=True, exist_ok=True)
            errors_path.write_text(json.dumps({
                "url": note_url,
                "method": "POST",
                "body": send_note,
                "response": {
                    "status_code": note_response.status_code,
                    "reason": note_response.reason,
                    "text": response_text,
                },
            }))
            logging.error(f"post note {note_url} saved error to {errors_path}")
            print("failed to post note")
            return
        else:
            raise

    print("note posted successfully")

    # update cache with new note
    new_notes.append(json.loads(response_text))
    new_notes_path.parent.mkdir(parents=True, exist_ok=True)
    new_notes_path.write_text(json.dumps(new_notes))


# method used to compare values between old and new incident notes
def check_count(id_old, id_new):

    old_notes_endpoint = old_base_api_url + "/v1/incidents/secrets/"f"{id_old}/notes"
    old_notes = []
    new_notes_endpoint = new_base_api_url + "/v1/incidents/secrets/"f"{id_new}/notes"
    new_notes = []

    old_notes_path = pathlib.Path(__file__).parent.joinpath(
        ".cache", "old_notes", f"{id_old}.json",
    )
    if old_notes_path.exists():
        old_notes = json.loads(old_notes_path.read_text())
    else:
        while True:
            old_note_response = backoff(requests.get)(old_notes_endpoint, headers={"Authorization": f"Token {old_token_instance}"})
            assert old_note_response.status_code == 200
            old_notes += old_note_response.json()
            if "next" not in old_note_response.links:
                break
            old_notes_endpoint = old_note_response.links["next"]["url"]
        old_notes_path.parent.mkdir(parents=True, exist_ok=True)
        old_notes_path.write_text(json.dumps(old_notes))

    new_notes_path = pathlib.Path(__file__).parent.joinpath(
        ".cache", "new_notes", f"{id_old}.json",
    )
    if new_notes_path.exists():
        new_notes = json.loads(new_notes_path.read_text())
    else:
        while True:
            new_note_response = backoff(requests.get)(new_notes_endpoint, headers={"Authorization": f"Token {new_token_instance}"})
            assert new_note_response.status_code == 200
            new_notes += new_note_response.json()
            if "next" not in new_note_response.links:
                break
            new_notes_endpoint = new_note_response.links["next"]["url"]
        new_notes_path.parent.mkdir(parents=True, exist_ok=True)
        new_notes_path.write_text(json.dumps(new_notes))

    count = len(new_notes) - len(old_notes)
    return count


for i in all_old_incidents:
    print("looking for an incident match for incident", i['id'])
    for j in all_new_incidents:
        if i['secret_hash'] == j['secret_hash']:
            print("incident match found, incident:", j['id'])

            # call the notes migration function
            notes_migration(i['id'], j['id'])
            Value = False

            if i['severity'] != j['severity']:
                payload = {'severity': i['severity']}
                body = json.dumps(payload)
                update_severity = new_base_api_url + "/v1/incidents/secrets/"f"{j['id']}"
                response = backoff(requests.patch)(update_severity, body, headers={"Authorization": f"Token {new_token_instance}", 'Content-Type': 'application/json; charset=UTF-8'})
                response_json = response.json()
                print(f"Updating severity body: {body}")
                print(f"Updating severity response: {response.status_code}: {response_json}")
                assert response.status_code == 200
                # if response.status_code == 409:
                #     assert "already ignored" in str(response_json)
                print("Severity updated")
                j['severity'] = i['severity']

            if i['status'] == 'TRIGGERED' and j['status'] != 'TRIGGERED':
                reopen_incident = new_base_api_url + "/v1/incidents/secrets/"f"{j['id']}/reopen"
                response = backoff(requests.post)(reopen_incident, headers={"Authorization": f"Token {new_token_instance}"})
                response_json = response.json()
                print(f"triggered : {response.status_code}: {response_json}")
                assert response.status_code in (200, 409)
                if response.status_code == 409:
                    assert "already open" in str(response_json)
                j['severity'] = i['severity']
                j['status'] = i['status']

            if i['status'] == 'TRIGGERED' and j['status'] == 'TRIGGERED':
                counter = check_count(i['id'], j['id'])
                if counter < 2:
                    Value = True

            if i['status'] == 'IGNORED' and j['status'] != 'IGNORED':
                ignore_payload = {'ignore_reason': i['ignore_reason']}
                body = json.dumps(ignore_payload)
                update_ignore = new_base_api_url + "/v1/incidents/secrets/"f"{j['id']}/ignore"
                response = backoff(requests.post)(update_ignore, body, headers={"Authorization": f"Token {new_token_instance}", 'Content-Type': 'application/json; charset=UTF-8'})
                response_json = response.json()
                print(f"ignored : {response.status_code}: {response_json}")
                assert response.status_code in (200, 409)
                if response.status_code == 409:
                    assert "already ignored" in str(response_json)
                print("ignore_reason: "f"{i['ignore_reason']}")
                print("id: "f"{i['id']}")
                print("ignore_date: "f"{i['ignored_at']}")
                resolution_note(i['ignore_reason'], i['id'], i['ignored_at'], j['id'], i['ignorer_id'])
                Value = True
                j['status'] = i['status']
                j['ignore_reason'] = i['ignore_reason']

            if i['status'] == 'ASSIGNED' and j['status'] != 'ASSIGNED':
                note = "Incident has been assigned to "f"{i['assignee_email']}"
                print(note)
                counter = check_count(i['id'], j['id'])
                if counter < 2:
                    post_note(note, j['id'])
                else:
                    print('assignee note already exists')
                Value = True
                j['status'] = i['status']

            if i['status'] == 'RESOLVED' and j['status'] not in ('RESOLVED', 'IGNORED'):
                resolve_payload = {'secret_revoked': i['secret_revoked']}
                body = json.dumps(resolve_payload)
                update_resolve = new_base_api_url + "/v1/incidents/secrets/"f"{j['id']}/resolve"
                response = backoff(requests.post)(update_resolve, body, headers={"Authorization": f"Token {new_token_instance}", 'Content-Type': 'application/json; charset=UTF-8'})
                response_json = response.json()
                print(f"resolved : {response.status_code}: {response_json}")
                assert response.status_code == 200
                resolution_note(i['secret_revoked'], i['id'], i['resolved_at'], j['id'], i['resolver_id'])
                Value = True
                j['status'] = i['status']
                j['secret_revoked'] = i['secret_revoked']
            if Value:
                print('success')
                success_note(i['id'], j['id'], i['gitguardian_url'], i['status'])
                all_new_incidents_path.write_text(json.dumps(all_new_incidents))
            else:
                print('incident already migrated')

            break
