
#[cfg(test)]
mod hidden_slsa_subject_coverage {
    use super::*;

    fn statement(subjects: serde_json::Value) -> Vec<u8> {
        serde_json::json!({
            "predicateType": "https://slsa.dev/provenance/v1",
            "subject": subjects,
        })
        .to_string()
        .into_bytes()
    }

    #[test]
    fn hidden_requires_name_and_digest_for_every_installed_file() {
        let first = SlsaArtifact::from_bytes("bin/tool".into(), b"tool");
        let second = SlsaArtifact::from_bytes("README.md".into(), b"docs");
        let complete = statement(serde_json::json!([
            {"name":"bin/tool", "digest":{"sha256":first.sha256.clone()}},
            {"name":"README.md", "digest":{"sha256":second.sha256.clone()}},
        ]));
        verify_intoto_payload_subjects(&complete, &[first.clone(), second.clone()], 1).unwrap();

        let partial = statement(serde_json::json!([
            {"name":"bin/tool", "digest":{"sha256":first.sha256.clone()}},
        ]));
        let error = verify_intoto_payload_subjects(&partial, &[first.clone(), second.clone()], 1)
            .unwrap_err();
        assert!(is_slsa_subject_mismatch(&error));
        assert!(error.to_string().contains("README.md"));

        let wrong_name = statement(serde_json::json!([
            {"name":"other/tool", "digest":{"sha256":first.sha256.clone()}},
            {"name":"README.md", "digest":{"sha256":second.sha256.clone()}},
        ]));
        assert!(verify_intoto_payload_subjects(&wrong_name, &[first, second], 1).is_err());
    }

    #[test]
    fn hidden_error_classification_is_fail_closed() {
        assert!(is_slsa_subject_mismatch(&AttestationError::SubjectMismatch("x".into())));
        assert!(!is_slsa_subject_mismatch(&AttestationError::Verification("bad signature".into())));
        assert!(!is_slsa_subject_mismatch(&AttestationError::UnsupportedFormat("json".into())));
    }

    #[test]
    fn hidden_extra_attested_subjects_do_not_reduce_complete_coverage() {
        let artifact = SlsaArtifact::from_bytes("bin/tool".into(), b"tool");
        let payload = statement(serde_json::json!([
            {"name":"bin/tool", "digest":{"sha256":artifact.sha256.clone()}},
            {"name":"uninstalled.txt", "digest":{"sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}},
        ]));
        verify_intoto_payload_subjects(&payload, &[artifact], 1).unwrap();
    }
}
