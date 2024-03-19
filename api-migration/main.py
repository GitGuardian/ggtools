import json
import requests
import time
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

# method used to retrieve all the incidents on the old instance
while True:
    response = requests.get(old_endpoint_url, headers={"Authorization": f"Token {old_token_instance}"})
    assert response.status_code == 200
    all_old_incidents += response.json()

    if "next" not in response.links:
        break

    old_endpoint_url = response.links["next"]["url"]
print("old incidents have been retrieved")


# method used to retrieve all incidents on the new instance
while True:
    response = requests.get(new_endpoint_url, headers={"Authorization": f"Token {new_token_instance}"})
    assert response.status_code == 200
    all_new_incidents += response.json()

    if "next" not in response.links:
        break

    new_endpoint_url = response.links["next"]["url"]
print("new incidents have been retrieved")


# notes migration method
def notes_migration(old_secret_id, new_secret_id):

    print("starting notes migration for incident", old_secret_id, "...")
    old_notes_endpoint = old_base_api_url + "/v1/incidents/secrets/"f"{old_secret_id}/notes"
    old_notes = []
    new_notes_endpoint = new_base_api_url + "/v1/incidents/secrets/"f"{new_secret_id}/notes"

    while True:
        note_response = requests.get(old_notes_endpoint, headers={"Authorization": f"Token {old_token_instance}"})
        assert note_response.status_code == 200
        old_notes += note_response.json()
        if "next" not in note_response.links:
            break
        old_notes_endpoint = response.links["next"]["url"]
    print("notes retrieved for "f"{old_secret_id}")

    if not old_notes:
        print("no notes on this incident")
        n = 0
    else:
        print(len(old_notes), "note(s) have been found for this incident")
        new_incident_note_response = requests.get(new_notes_endpoint, headers={"Authorization": f"Token {new_token_instance}"})
        assert new_incident_note_response.status_code == 200
        new_notes = new_incident_note_response.json()
        n = len(new_notes)

        if len(new_notes) == len(old_notes):
            print("Notes for incident", old_secret_id, "have been migrated before, skipping...")

        while n < len(old_notes):
            member_endpoint = old_base_api_url + "/v1/members/"f"{old_notes[n]['member_id']}"
            member_response = requests.get(member_endpoint, headers={"Authorization": f"Token {old_token_instance}"})
            assert response.status_code == 200
            member = member_response.json()
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

    if counter == 0:
        note = "incident " f"{old_secret_id}" " note(s) (if any exist) have been successfully migrated"
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
    member_endpoint = old_base_api_url + "/v1/members/"f"{member_id}"
    member_response = requests.get(member_endpoint, headers={"Authorization": f"Token {old_token_instance}"})
    assert response.status_code == 200
    member = member_response.json()
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
    note_url = new_base_api_url + "/v1/incidents/secrets/"f"{new_id}""/notes"
    send_note = {"comment": note}
    body = json.dumps(send_note)
    note_response = requests.post(note_url, body, headers={"Authorization": f"Token {new_token_instance}", 'Content-Type': 'application/json; charset=UTF-8'})
    assert note_response.status_code == 201
    print("note posted successfully")


# method used to compare values between old and new incident notes
def check_count(id_old, id_new):

    old_notes_endpoint = old_base_api_url + "/v1/incidents/secrets/"f"{id_old}/notes"
    old_notes = []
    new_notes_endpoint = new_base_api_url + "/v1/incidents/secrets/"f"{id_new}/notes"
    new_notes = []
    while True:
        old_note_response = requests.get(old_notes_endpoint, headers={"Authorization": f"Token {old_token_instance}"})
        assert old_note_response.status_code == 200
        old_notes += old_note_response.json()
        if "next" not in old_note_response.links:
            break
        old_notes_endpoint = old_note_response.links["next"]["url"]

    while True:
        new_note_response = requests.get(new_notes_endpoint, headers={"Authorization": f"Token {new_token_instance}"})
        assert new_note_response.status_code == 200
        new_notes += new_note_response.json()
        if "next" not in new_note_response.links:
            break
        new_notes_endpoint = new_note_response.links["next"]["url"]

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
                update_severity = new_base_api_url + "/v1/incidents/secrets/"f"{j['id']}"
                response = requests.patch(update_severity, payload, headers={"Authorization": f"Token {new_token_instance}"})
                print("Updating severity response: ", response.status_code)
                assert response.status_code == 200
                print("Severity updated")

            if i['status'] == 'TRIGGERED' and j['status'] != 'TRIGGERED':
                reopen_incident = new_base_api_url + "/v1/incidents/secrets/"f"{j['id']}/reopen"
                response = requests.post(reopen_incident, headers={"Authorization": f"Token {new_token_instance}"})
                print("triggered :", response.status_code)
                assert response.status_code == 200

            if i['status'] == 'TRIGGERED' and j['status'] == 'TRIGGERED':
                counter = check_count(i['id'], j['id'])
                if counter < 2:
                    Value = True

            if i['status'] == 'IGNORED' and j['status'] != 'IGNORED':
                ignore_payload = {'ignore_reason': i['ignore_reason']}
                update_ignore = new_base_api_url + "/v1/incidents/secrets/"f"{j['id']}/ignore"
                response = requests.post(update_ignore, ignore_payload, headers={"Authorization": f"Token {new_token_instance}"})
                print("ignored :", response.status_code)
                assert response.status_code == 200
                print("ignore_reason: "f"{i['ignore_reason']}")
                print("id: "f"{i['id']}")
                print("ignore_date: "f"{i['ignored_at']}")
                resolution_note(i['ignore_reason'], i['id'], i['ignored_at'], j['id'], i['ignorer_id'])
                Value = True

            if i['status'] == 'ASSIGNED' and j['status'] != 'ASSIGNED':
                note = "Incident has been assigned to "f"{i['assignee_email']}"
                print(note)
                counter = check_count(i['id'], j['id'])
                if counter < 2:
                    post_note(note, j['id'])
                else:
                    print('assignee note already exists')
                Value = True

            if i['status'] == 'RESOLVED' and j['status'] != 'RESOLVED':
                resolve_payload = {'secret_revoked': i['secret_revoked']}
                update_resolve = new_base_api_url + "/v1/incidents/secrets/"f"{j['id']}/resolve"
                response = requests.post(update_resolve, resolve_payload, headers={"Authorization": f"Token {new_token_instance}"})
                print("resolved :", response.status_code)
                assert response.status_code == 200
                resolution_note(i['secret_revoked'], i['id'], i['resolved_at'], j['id'], i['resolver_id'])
                Value = True
            if Value:
                print('success')
                success_note(i['id'], j['id'], i['gitguardian_url'], i['status'])
            else:
                print('incident already migrated')

            break
    time.sleep(1)
