mod common;

use std::time::Duration;

use common::lsp_client::{file_uri, TestClient};

fn schema_path() -> String {
    format!("{}/tests/composition-hidden-schema.json", env!("CARGO_MANIFEST_DIR"))
}

fn doc_uri() -> String {
    file_uri(&format!("{}/tests/composition-hidden-doc.json", env!("CARGO_MANIFEST_DIR")))
}

fn document(body: &str) -> String {
    format!(r#"{{"$schema": "{}", {body}}}"#, schema_path())
}

async fn complete(content: &str, cursor: usize) -> Vec<String> {
    let mut client = TestClient::new();
    client.initialize().await;
    let uri = doc_uri();
    client.did_open(&uri, "json", 1, content).await;
    tokio::time::sleep(Duration::from_millis(300)).await;
    client.recv_notification("textDocument/publishDiagnostics").await;
    let result = client.completion(&uri, 0, cursor as u32).await;
    result["items"]
        .as_array()
        .expect("completion items")
        .iter()
        .map(|item| item["label"].as_str().expect("label").to_owned())
        .collect()
}

async fn property_labels(property: &str) -> Vec<String> {
    let body = format!(r#""{property}": {{}}"#);
    let content = document(&body);
    let needle = format!(r#""{property}": {{"#);
    let cursor = content.find(&needle).unwrap() + needle.len();
    complete(&content, cursor).await
}

async fn value_labels(property: &str) -> Vec<String> {
    let body = format!(r#""{property}": null"#);
    let content = document(&body);
    let needle = format!(r#""{property}": "#);
    let cursor = content.find(&needle).unwrap() + needle.len();
    complete(&content, cursor).await
}

#[tokio::test]
async fn hidden_allof_merges_object_properties() {
    let labels = property_labels("all_object").await;
    assert!(labels.contains(&"alpha".into()), "{labels:?}");
    assert!(labels.contains(&"beta".into()), "{labels:?}");
}

#[tokio::test]
async fn hidden_oneof_merges_object_properties() {
    let labels = property_labels("one_object").await;
    assert!(labels.contains(&"left".into()), "{labels:?}");
    assert!(labels.contains(&"right".into()), "{labels:?}");
}

#[tokio::test]
async fn hidden_anyof_merges_only_branch_properties() {
    let labels = property_labels("any_object").await;
    for expected in ["north", "south"] {
        assert!(labels.contains(&expected.into()), "missing {expected}: {labels:?}");
    }
    for forbidden in ["alpha", "left", "decoy_sibling"] {
        assert!(!labels.contains(&forbidden.into()), "leaked {forbidden}: {labels:?}");
    }
}

#[tokio::test]
async fn hidden_nested_anyof_and_null() {
    let body = r#""nested": {"choice": null}"#;
    let content = document(body);
    let needle = r#""choice": "#;
    let cursor = content.find(needle).unwrap() + needle.len();
    let labels = complete(&content, cursor).await;
    for expected in ["true", "false", "null"] {
        assert!(labels.contains(&expected.into()), "missing {expected}: {labels:?}");
    }
}

#[tokio::test]
async fn hidden_ref_inside_allof_is_resolved() {
    let labels = property_labels("ref_object").await;
    assert!(labels.contains(&"from_ref".into()), "{labels:?}");
    assert!(labels.contains(&"local".into()), "{labels:?}");
}

#[tokio::test]
async fn hidden_array_type_contributes_each_value_kind() {
    let labels = value_labels("typed_nullable").await;
    for expected in ["true", "false", "null"] {
        assert!(labels.contains(&expected.into()), "missing {expected}: {labels:?}");
    }
}

#[tokio::test]
async fn hidden_composed_values_are_deduplicated_deterministically() {
    let labels = value_labels("deduplicated").await;
    for expected in [r#""same""#, r#""left""#, r#""right""#] {
        assert!(labels.contains(&expected.into()), "missing {expected}: {labels:?}");
    }
    assert_eq!(labels.iter().filter(|label| label.as_str() == r#""same""#).count(), 1, "{labels:?}");

    let repeated = value_labels("deduplicated").await;
    assert_eq!(labels, repeated, "completion order changed across fresh servers");
}

#[tokio::test]
async fn hidden_cross_kind_values_deduplicate_by_final_label() {
    let labels = value_labels("cross_kind_deduplicated").await;
    assert!(labels.contains(&r#""same""#.into()), "{labels:?}");
    assert!(labels.contains(&r#""other""#.into()), "{labels:?}");
    assert_eq!(labels.iter().filter(|label| label.as_str() == r#""same""#).count(), 1, "{labels:?}");
}

#[tokio::test]
async fn hidden_existing_property_is_not_suggested_again() {
    let body = r#""all_object": {"alpha": true, }"#;
    let content = document(body);
    let needle = r#"true, "#;
    let cursor = content.find(needle).unwrap() + needle.len();
    let labels = complete(&content, cursor).await;
    assert!(!labels.contains(&"alpha".into()), "existing key leaked: {labels:?}");
    assert!(labels.contains(&"beta".into()), "missing unused key: {labels:?}");
}
