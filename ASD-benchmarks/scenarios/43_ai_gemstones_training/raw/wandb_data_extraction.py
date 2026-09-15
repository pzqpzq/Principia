import wandb
import pandas as pd


def call_wandb_to_get_data():
    # Specify the WandB project path
    project_path = "tomg-group-umd/scaling_laws"

    # Initialize an API object
    api = wandb.Api()

    # Fetch the project
    runs = api.runs(project_path)

    # Extract summary metrics that start with "scaling/"
    summary_list = []
    # Most of these bad runs are from failed starts across many nodes, some where stated are to remove exploded runs
    bad_runs = [
        "14sgx18p",
        "pm8qhk54",
        "8qvhq0uk",
        "c7hnngtx",
        "0i1sn2l4",
        "nug96soa",
        "bib1tmzn",
        "h0r8w6ei",
        "5d68a1yz",
        "7yflx9w7",
        "3at4wp1q",
        "xrc0mkk8",
    ]

    # cooler runs bad list
    bad_runs += [
        "bi7vjhr6",
        "dnn7k5aq",
        "7equplfy",
        "73w8mbdu",
        "ud20j038",
        "jvnkpydi",
        "vc4etelb",
    ]

    # runs which diverged after 100B
    bad_runs += [
        # 2560x8
        "48x5i2js",
        "g0y180ol",
        "udombjfr",
        "8rlhzsem",
        "rs29972v",
        "66mgs2wt",
        "8qvhq0uk",
        "wbjpmto8",
        "ck1bx7h4",
        "cqqxfi6b",
        "arti9yvh",
        "thcetf5e",
        "t0u84wnd",
        "11bh6o7n",
        "0dspcke6",
        "3lf9qvsn",
        "ls4kitx3",
        # 3072x12
        "3ne9l4cn",
        "ghm2iqud",
        "njjv2s08",
        "xrc0mkk8",
        "cwce0g3r",
        "crvy1iif",
        "a6vxta4i",
        "yh1nqa11",
        "pvd4ckan",
        "cltzfquc",
        "xijwqeot",
        "b4nxme21",
        "26q6bwqv",
    ]

    # bad runs from extended
    bad_runs += [
        "kmlu51rs",
        "8x6i2mzd",
        "q1nzvf8f",
        "rg1jombr",
        "fxy6ghb0",
        "pvzro271",
        "tptxnlb4",
        "6ldgyrtx",
        "cgsfwf07",
        "8d2n47ra",
        "zvaw4qf7",
        "paeigi15",
        "d01l5nje",
        "2tbihit3",
        "424tmg1f",
        "qaa7i1fz",
        "nwq3c8er",
        # all failed 3072x12 runs
        "h5xo33e1",
        "7las1gnb",
        "hdrvdq18",
        "qznb20mr",
        "b9xroqyc",
        "rc9k3pq7",
        "w922kmzf",
        "q9s2d8vm",
        "p69paenz",
        "eu76ucc2",
        "j13kb38x",
        "p5onbg7x",
        "dcgig95q",
        "70wo2jpv",
        "owk4wooi",
        "b2y20ok4",
        "s7a4ucc8",
        # no longer 3072x12
        "2i0nj0fe",
    ]
    bad_runs += ["u7o059p1", "dc32n8sd", "1vh2n000"]  # 1792x18 explosion
    ckpt_key_strings = [
        2385,
        4770,
        7155,
        9540,
        11925,
        14310,
        16695,
        19080,
        21465,
        23840,
    ]

    step_postfixes = [f"_{i:08d}" for i in ckpt_key_strings]

    for run in runs:
        if run.id in bad_runs:
            continue

        run_tags = run.tags

        if (("big_red_button" in run_tags) or ("big_cool_button" in run_tags)) and (
            "cooldown_ablation" not in run_tags
        ):
            # currently takes all but the the cooldown_ablation runs
            """
            # base hot runs for the 16 original models (minus the exploded 1792x7 run via bad_list)
            tags=[big_red_button,pretrain,v0]

            # each of the 10B cooldown runs for the 16 original models (minus the 1792x7 children which we never actually ran, I believe)
            tags=[big_red_button,cooldown,v0]

            # base hot runs for the 4 new model shapes, plus the redo of the 1792x7 (at implicitly reduced lr)
            tags=[big_red_button,pretrain,v1]

            # each of the 10B cooldown runs for the 4 new model shapes, plus the redo of the 1792x7 (at implicitly reduced lr)
            tags=[big_red_button,cooldown,v1]

            # two selected models, at varying starting points cooled for varying amounts (the weird _XXXXX_XXXXX suffix scheme)
            tags=[big_red_button,cooldown,cooldown_ablation,v0]

            # lr/2 runs
            tags=['big_cool_button', 'pretrain', 'v0']
            """
            summary = {}

            # Extract and store global_loss indexed by step
            history = run.history(keys=["optimizer_step", "global_loss"], pandas=True)
            # Check if the history DataFrame is not empty
            if not history.empty:
                # Index by "optimiser_step" and create the dictionary
                summary["global_loss_by_optimiser_step"] = history.set_index(
                    "optimizer_step"
                )["global_loss"].to_dict()

            # Extract and store the last value of val_loss
            val_loss_history = run.history(
                keys=["optimizer_step", "val_loss"], pandas=True
            )
            if not val_loss_history.empty:
                summary["val_loss_by_optimiser_step"] = val_loss_history.set_index(
                    "optimizer_step"
                )["val_loss"].to_dict()

            # Extract summary metrics starting with "scaling/" and remove the prefix
            for key, value in run.summary._json_dict.items():
                if key.startswith("scaling/"):
                    if "global_loss" in key:
                        continue
                    new_key = key.replace("scaling/", "")
                    summary[new_key] = value

            print(run.id)
            total_node_hrs = run.summary["cost_basis/total_node_hours"]
            total_wall_hrs = run.summary["cost_basis/total_wall_hours"]
            summary["num_nodes"] = (
                round(int(total_node_hrs / total_wall_hrs) / 2) * 2
            )  # round to 2
            summary["num_gpus"] = summary["num_nodes"] * 8

            block_size = 2048
            world_batch_size = 2048
            tokens = run.summary["optimizer_step"] * block_size * world_batch_size
            tokens_from_wandb = run.summary["total_tokens"]
            assert (
                tokens == tokens_from_wandb
            ), f"Run {run.name} has a token count mismatch. Should be {tokens} but logged as {tokens_from_wandb}"
            summary["tokens"] = tokens

            summary["seconds_per_step"] = run.summary["seconds/step"]
            summary["run_id"] = run.id
            summary["pretrain"] = True if "pretrain" in run_tags else False
            summary["cooldown"] = True if "cooldown" in run_tags else False
            summary["lr_ablation"] = True if "big_cool_button" in run_tags else False

            def remove_postfixes_from_string(input_string, postfixes):
                for postfix in postfixes:
                    input_string = input_string.replace(postfix, "")
                return input_string

            summary["run_name"] = remove_postfixes_from_string(run.name, step_postfixes)
            summary_list.append(summary)

    # Convert to DataFrame
    summary_df = pd.DataFrame(summary_list)
    summary_df = summary_df.sort_values(by="run_name")
    return summary_df


OUTPUT_NAME = f"wandb_dfs/summary_df.jsonl"
# summary_df = call_wandb_to_get_data()
# summary_df.to_json(OUTPUT_NAME, orient="records", lines=True)
summary_df = pd.read_json(OUTPUT_NAME, orient="records", lines=True)

print(summary_df.columns)
print(summary_df.shape)


## merge runs over name
def merge_dicts(dicts):
    merged = {}
    for d in dicts:
        for k, v in d.items():
            if k in merged.keys():
                if abs(merged[k] - v) > 0.2:
                    print("Merging dicts for these rows:", dicts.index)
                    print(f"overlapping keys too far apart {merged[k]} and {v} for {k}")
                    exit()
            merged[k] = v
    sorted_dict = {k: merged[k] for k in sorted(merged)}
    return sorted_dict


def assert_same(series):
    unique_values = series.unique()
    assert (
        len(unique_values) == 1
    ), f"Values differ in column '{series.name}': {unique_values}"
    return unique_values[0]


def merge_lists(elements):
    merged = []
    for element in elements:
        merged.append(element)
    return merged


def take_max(maxs):
    elements = []
    for max_el in maxs:
        elements.append(max_el)
    return max(elements)


def take_min(mins):
    elements = []
    for min_el in mins:
        elements.append(min_el)
    return min(elements)


# Define aggregation functions for specified columns
agg_funcs = {
    "global_loss_by_optimiser_step": lambda x: merge_dicts(x),
    "val_loss_by_optimiser_step": lambda x: merge_dicts(x),
    "tokens": "sum",
    "seconds_per_step": "mean",
    "run_id": lambda x: merge_lists(x),
    "max_lr": lambda x: take_max(x),
    "max_lr_scaled": lambda x: take_max(x),
    "min_lr": lambda x: take_min(x),
    "min_lr_scaled": lambda x: take_min(x),
}

# For all other columns, use the assert_same function
for col in summary_df.columns:
    if col not in agg_funcs and col not in [
        "run_name",
        "pretrain",
        "cooldown",
        "lr_ablation",
    ]:
        agg_funcs[col] = assert_same


def calculate_mean_without_outliers(group):
    """
    take mean over seconds per step ignoring extreme outliers
    """
    lower_bound = group["seconds_per_step"].quantile(0.05)
    upper_bound = group["seconds_per_step"].quantile(0.95)
    filtered_group = group[
        (group["seconds_per_step"] >= lower_bound)
        & (group["seconds_per_step"] <= upper_bound)
    ]
    return filtered_group["seconds_per_step"].mean()


summary_df["clean_run_name"] = summary_df["run_name"].str.replace(
    "^cooler_", "", regex=True
)  # want to group over lr/2 runs too so remove the cooler_ prefix
grouped_means = (
    summary_df.groupby("clean_run_name")
    .apply(calculate_mean_without_outliers)
    .to_dict()
)  # mean while removing extreme outliers
summary_df = summary_df.drop(columns=["clean_run_name"])  # not needed anymore
summary_df["seconds_per_step"] = (
    summary_df["run_name"].str.replace("^cooler_", "", regex=True).map(grouped_means)
)

orginal_summary_df = summary_df
for temperature in [
    "hot_477",
    "all",
    "cool_begin",
    "cool_end",
    "hot",
    "lr_ablation_hot",
    "lr_ablation_hot_477",
    "hot_100b+",
    "hot_100b+_477",
    "hot_120b+_only",
    "hot_120b+_only_477",
    "hot_100b+_512x",
]:
    summary_df = orginal_summary_df.copy(deep=True)
    if "lr_ablation" in temperature:
        summary_df = summary_df[summary_df["lr_ablation"] == True]
    else:
        summary_df = summary_df[summary_df["lr_ablation"] == False]

    if "cool" in temperature:
        summary_df = summary_df[summary_df["cooldown"] == True]
    elif "hot" in temperature:
        summary_df = summary_df[summary_df["cooldown"] == False]

    if "512x" in temperature:
        summary_df = summary_df[summary_df["run_name"].str.contains("512x", na=False)]

    grouped_df = (
        summary_df.groupby(["run_name", "pretrain", "cooldown"])
        .agg(agg_funcs)
        .reset_index()
    )

    grouped_df["global_loss"] = grouped_df["global_loss_by_optimiser_step"].apply(
        lambda d: d[max(d.keys())] if isinstance(d, dict) else None
    )

    grouped_df["val_loss"] = grouped_df["val_loss_by_optimiser_step"].apply(
        lambda d: d[max(d.keys())] if isinstance(d, dict) else None
    )

    if temperature == "all":
        grouped_df.to_json("wandb_dfs/wandb_df_raw.jsonl", orient="records", lines=True)
        continue

    def extract_val_loss_by_steps(df, steps):
        # Initialize an empty DataFrame to store the results
        extracted_df = []

        # Loop over each row in the DataFrame
        for idx, row in df.iterrows():
            # Extract the val_loss_by_optimiser_step dictionary
            val_loss_dict = row["val_loss_by_optimiser_step"]
            val_loss_dict = {int(k): v for k, v in val_loss_dict.items()}

            # Loop through the specific steps to extract values
            for step in steps:
                if (step in [26223]) and (
                    row["run_name"] == "PyGemma-3072x12_pretrain"
                ):  # never cooled this one down
                    continue

                if step not in val_loss_dict:
                    print(f"not found: {step} for {row['run_name']}")
                    continue  # missing that step .. Frontier :(

                # Create a dictionary to store the extracted values for this step
                extracted_values = {
                    "run_name": row["run_name"],
                    "params_active_precise": row["params"],
                    "width": row["width"],
                    "depth": row["depth"],
                    "tokens": step * 2048 * 2048,  # step * batch size * context length
                }
                extracted_values |= {
                    "step": step,
                    "num_nodes": row["num_nodes"],
                    "seconds_per_step": row["seconds_per_step"],
                }

                # Extract the value for this specific step
                extracted_values[f"final_loss"] = val_loss_dict.get(
                    step, None
                )  # final val loss

                # Append the extracted values to the result DataFrame
                extracted_df.append(extracted_values)

        return pd.DataFrame(extracted_df)

    ckpt_key_strings_plus_10pct = [
        2622,
        5246,
        7870,
        10493,
        13116,
        15740,
        18364,
        20987,
        23610,
        26223,
    ]

    if temperature in ["hot_477"]:
        # every 477 up to 100b
        ckpt_key_strings = [i for i in range(477, 23851, 477)]
    elif temperature in ["hot"]:
        # every 2385 up to 100b
        ckpt_key_strings = [i for i in range(2385, 23851, 2385)]
    elif temperature in ["lr_ablation_hot", "cool_begin"]:
        # old chkpt strings end at 23840, not 23850
        ckpt_key_strings = [i for i in range(2385, 23841, 2385)] + [23840]
    elif temperature == "cool_end":
        ckpt_key_strings = ckpt_key_strings_plus_10pct
    elif temperature in ["lr_ablation_hot_477"]:
        # old chkpt strings end at 23840, not 23850
        ckpt_key_strings = [i for i in range(477, 23841, 477)] + [23840]
    elif temperature in ["hot_100b+", "hot_100b+_512x"]:
        # every 2385, up to 350b
        ckpt_key_strings = [i for i in range(2385, 83476, 2385)]
    elif temperature in ["hot_100b+_477"]:
        # every 477 up to 350b
        ckpt_key_strings = [i for i in range(477, 83476, 477)]
    elif temperature in ["hot_120b+_only"]:
        # every 2385, up to 350b from 120b
        ckpt_key_strings = [i for i in range(28620, 83476, 2385)]
    elif temperature in ["hot_120b+_only_477"]:
        # every 2385, up to 350b from 120b
        ckpt_key_strings = [i for i in range(28620, 83476, 477)]
    else:
        print("temp not found")
        exit()

    extracted_df = extract_val_loss_by_steps(grouped_df, ckpt_key_strings)

    print(extracted_df.iloc[:, :10].head(10))
    print(extracted_df.shape)

    OUTPUT_NAME = f"wandb_dfs/wandb_df_for_fitting_{temperature}.jsonl"
    extracted_df.to_json(OUTPUT_NAME, orient="records", lines=True)
