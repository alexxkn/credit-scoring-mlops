import src.data.make_dataset as make_dataset


def test_clean_data_maps_undocumented_codes(raw_data):
    raw_data.loc[0, ["EDUCATION", "MARRIAGE"]] = [0, 0]
    raw_data.loc[1, "EDUCATION"] = 5
    raw_data.loc[2, "EDUCATION"] = 6
    cleaned = make_dataset.clean_data(raw_data)
    assert set(cleaned["EDUCATION"]) <= {1, 2, 3, 4}
    assert set(cleaned["MARRIAGE"]) <= {1, 2, 3}
    assert cleaned.loc[0, "EDUCATION"] == 4 and cleaned.loc[0, "MARRIAGE"] == 3


def test_clean_data_drops_id_and_renames_target(raw_data):
    cleaned = make_dataset.clean_data(raw_data)
    assert "ID" not in cleaned.columns
    assert make_dataset.TARGET in cleaned.columns
    assert make_dataset.RAW_TARGET not in cleaned.columns
    assert len(cleaned) == len(raw_data)


def test_split_data_is_stratified(raw_data):
    cleaned = make_dataset.clean_data(raw_data)
    train, test = make_dataset.split_data(cleaned, test_size=0.2, random_state=42)
    assert len(train) + len(test) == len(cleaned)
    assert abs(train[make_dataset.TARGET].mean() - test[make_dataset.TARGET].mean()) < 0.02
