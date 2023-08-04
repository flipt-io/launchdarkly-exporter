import os
import requests
import yaml

base_url = "https://app.launchdarkly.com/api/v2"
api_key = os.environ.get("LAUNCHDARKLY_API_KEY")

constraint_operators = {"endsWith": "suffix", "startsWith": "prefix"}


def get_flags():
    headers = {
        "Authorization": api_key,
    }

    response = requests.get(f"{base_url}/flags/default", headers=headers)

    flags_response = response.json()

    flags = []

    for flag in flags_response["items"]:
        flags.append(
            {
                "key": flag["key"],
                "name": flag["name"],
            }
        )

    return flags


def retrieve_flipt_models(input_flags):
    headers = {
        "Authorization": api_key,
    }

    segment_counter = 1
    documents_map = {}
    environment_to_segments = {}

    for intermediate_flag in input_flags:
        response = requests.get(
            f"{base_url}/flags/default/{intermediate_flag['key']}", headers=headers
        )
        flag_response = response.json()

        flag = {}

        # We do not support percentage based rollouts on segmentation for "boolean"
        # but LaunchDarkly does. So we will use the VARIANT_FLAG_TYPE for all flags.
        flag["key"] = flag_response["key"]
        flag["type"] = "VARIANT_FLAG_TYPE"
        flag["name"] = flag_response["name"]
        flag["description"] = flag_response["description"]
        flag["enabled"] = True

        # Variants
        variants = []
        for variant in flag_response["variations"]:
            variants.append({"key": variant["value"], "name": variant["value"]})

        flag["variants"] = variants

        # Rules & (Flipt) Segments
        environments = flag_response["environments"]

        for environment in environments:
            # One time call to get Segments from LaunchDarkly for each environment.
            if environment not in environment_to_segments:
                segments_response = requests.get(
                    f"{base_url}/segments/default/{environment}", headers=headers
                )
                segments_response_json = segments_response.json()
                segments = []
                for intermediate_segment in segments_response_json["items"]:
                    segment_key = intermediate_segment["key"]
                    for rule in intermediate_segment["rules"]:
                        constraints = []
                        for clause in rule["clauses"]:
                            constraint = {
                                "type": "STRING_COMPARISON_TYPE",
                                "property": clause["attribute"],
                                "operator": constraint_operators[clause["op"]]
                                if clause["op"] in constraint_operators
                                else "eq",
                                "value": clause["values"][0],
                            }
                            constraints.append(constraint)
                    segment = {
                        "key": segment_key,
                        "name": segment_key,
                        "constraints": constraints,
                        "match_type": "ALL_MATCH_TYPE",
                    }

                    segments.append(segment)

                environment_to_segments[environment] = segments

            # We have to create a new segment for each rule due to our API
            rules = []
            segments = []
            for rule in environments[environment]["rules"]:
                constraints = []

                for clause in rule["clauses"]:
                    # Get attribute, operator, and values
                    constraint = {
                        "type": "STRING_COMPARISON_TYPE",
                        "property": clause["attribute"],
                        "operator": "eq",  # clause["op"],
                        "value": clause["values"][0],
                    }

                    constraints.append(constraint)

                segment_key = f"segment_00{segment_counter}"
                segments.append(
                    {
                        "key": segment_key,
                        "name": segment_key,
                        "constraints": constraints,
                        "match_type": "ALL_MATCH_TYPE",
                    }
                )
                segment_counter += 1

                # Distributions
                distributions = []

                # If the key "rollout" exists it is a percentage based rollout
                # else single variate.
                if "rollout" in rule:
                    for rollout in rule["rollout"]["variations"]:
                        distributions.append(
                            {
                                "variant": variants[rollout["variation"]]["key"],
                                "rollout": float(rollout["weight"] / 1000),
                            }
                        )
                else:
                    distributions.append(
                        {
                            "variant": variants[rule["variation"]]["key"],
                            "rollout": 100.0,
                        }
                    )

                rules.append(
                    {
                        "segment": segment_key,
                        "distributions": distributions,
                    }
                )

            if environment in documents_map:
                documents_map[environment]["flags"].append({**flag, "rules": rules})
                documents_map[environment]["segments"].extend(segments)
            else:
                documents_map[environment] = {
                    "namespace": environment,
                    "flags": [{**flag, "rules": rules}],
                    "segments": segments,
                }

    for env in environment_to_segments:
        documents_map[env]["segments"].extend(environment_to_segments[env])

    documents = []

    for document in documents_map:
        documents.append(documents_map[document])

    return documents


if __name__ == "__main__":
    if api_key == None:
        print("Please provide LAUNCHDARKLY_API_KEY")
        exit(1)

    flags = get_flags()
    documents = retrieve_flipt_models(flags)

    for document in documents:
        with open(f"{document['namespace']}.features.yaml", "w") as file:
            yaml.dump(document, file, default_flow_style=False, sort_keys=False)
