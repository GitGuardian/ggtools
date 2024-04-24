# Incidents Migration Procedure
# Introduction:

This document details the requirements of what can be migrated when users want to switch from one GitGuardian instance to another. 

The proposed flow would be to leverage the GitGuardian API to manage a proper mirroring of the information from an old instance to a new one, without the need to recreate the Database objects, and having the GitGuardian application naturally update the values of the incident fields.

The switch could be from :

- SaaS <-> Self-Hosted
- Self-Hosted -> Self-Hosted
- SaaS -> SaaS

# Pre-requisites:

The migration would be required to have 2 instances that contain the same incident information for the migration to be efficient. 

To do so, the users would be required to integrate the sources they have from **instance A** on **instance B**

The sources will be scanned in **instance B** to list the same incidents of **instance A**

An API key with read permissions on incidents and members is required from **instance A**

the value should be introduced in the script via an env variable under `old_token_instance = os.environ.get("old_token_instance")`


An API key with read, write permissions on incidents is required from **instance B**

the value should be introduced in the script via an env variable under `new_token_instance = os.environ.get("new_token_instance")`


The script has fields tied to the `old_base_api_url` i.e. **workspace A** and `new_base_api_url` i.e. **workspace B** which should be changed to correspond to the url of the instances that need to be communicated with. 

If the instance is Onprem then the `base_api_url` should have `/exposed` appended to it

If the instance is SaaS then the `base_api_url` is `https://api.gitguardian.com`

# What the script does:

The a script is capable of running an incidents migration via API :

The script should be able to retrieve the incidents details from a single **workspace A** and mirror it in **workspace B**

The script will run to do the following :

- Takes the **TRIGGERED** state of **incidents A** and leaves a note on **incidents B** with :
    - Confirmation of migration with a reference to old incident id (link to **gitguardian_url A**)
- Takes only the **RESOLVED/IGNORED** state of **incidents A** and updates them in **incidents B** via API
    - If response 200 , will leave a note stating additional information on :
        - If resolved : the resolve_email with the timestamp
            - if response 200 will leave an additional note stating success with reference to old incident id (link to **gitguardian_url A**)
        - if ignored : the ignore_email with the timestamp
            - if response 200 will leave an additional note stating success with reference to old incident id (link to **gitguardian_url A**)
- Takes the **ASSIGNED** state of incidents A and leaves a note in incidents B via API with assignee email
    - if response 200 will leave an additional note stating success with reference to old incident id (link to **gitguardian_url A**)
- Takes the **NOTES** in **incidents A** and updates them in **incidents B** via API
    - provides the member email of the note and provides a timestamp with the note comment
    - A note is left on the incident with confirmation of successful notes migration
- Takes the assigned **SEVERITY** status of **incidents A** and updates it in **incidents B**

# What the script does not do:

- Migrate the Members of **workspace A** to **workspace B,** this decision is left to the end user, as members might not have the same mirrored permissions, so the script cannot anticipate the creation of members from one workspace to another
- Assigns **incidents B** with the same assignees of **incidents A**
    - This logic can be adapted to be included, but this has been designed to avoid any edge cases where the members on **workspace A** might have not been fully migrated to **workspace B**
- Migrate the information related to feedback loops (DITL)
- Migrate Audit logs
- Migrate Configuration Settings (SAML configuration, VCS integrations, Detector configuration, file path exclusions, notification systems, Created API keys, playbook settings…)

# Limitations:

No API limitations recorded so far..
