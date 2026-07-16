
#[cfg(test)]
mod hidden_archive_content_security {
    use super::*;
    use std::io::Write as _;

    fn tar_with(entries: &[(&str, &[u8])]) -> (tempfile::TempDir, std::path::PathBuf) {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("fixture.tar");
        let file = File::create(&path).unwrap();
        let mut builder = tar::Builder::new(file);
        for (name, bytes) in entries {
            let mut header = tar::Header::new_gnu();
            header.set_path(name).unwrap();
            header.set_size(bytes.len() as u64);
            header.set_mode(0o755);
            header.set_cksum();
            builder.append(&header, *bytes).unwrap();
        }
        builder.finish().unwrap();
        drop(builder);
        (dir, path)
    }

    #[test]
    fn hidden_hashes_every_regular_file_and_applies_strip() {
        let (_dir, path) = tar_with(&[("pkg/bin/tool", b"tool"), ("pkg/README.md", b"docs")]);
        let files = archive_content_files(&path, TarFormat::Tar, 1).unwrap();
        let values = files.into_iter().map(|f| (f.name, f.sha256)).collect::<std::collections::HashMap<_, _>>();
        assert_eq!(values.len(), 2);
        assert_eq!(values["bin/tool"], hex::encode(Sha256::digest(b"tool")));
        assert_eq!(values["README.md"], hex::encode(Sha256::digest(b"docs")));
    }

    #[test]
    fn hidden_rejects_duplicate_installed_paths() {
        let (_dir, path) = tar_with(&[("pkg/tool", b"one"), ("pkg/tool", b"two")]);
        let error = archive_content_files(&path, TarFormat::Tar, 1).unwrap_err().to_string();
        assert!(error.contains("duplicate"), "{error}");
    }

    #[test]
    fn hidden_rejects_symlink_hardlink_and_special_entries() {
        for kind in [tar::EntryType::Symlink, tar::EntryType::Link, tar::EntryType::Fifo] {
            let dir = tempfile::tempdir().unwrap();
            let path = dir.path().join("fixture.tar");
            let mut builder = tar::Builder::new(File::create(&path).unwrap());
            let mut header = tar::Header::new_gnu();
            header.set_entry_type(kind);
            header.set_path("pkg/entry").unwrap();
            if kind.is_symlink() || kind.is_hard_link() {
                header.set_link_name("pkg/target").unwrap();
            }
            header.set_size(0);
            header.set_mode(0o777);
            header.set_cksum();
            builder.append(&header, std::io::empty()).unwrap();
            builder.finish().unwrap();
            drop(builder);
            let error = archive_content_files(&path, TarFormat::Tar, 0).unwrap_err().to_string();
            assert!(error.contains("non-regular"), "{kind:?}: {error}");
        }
    }

    #[test]
    fn hidden_rejects_empty_and_fully_stripped_archives() {
        let (_dir, path) = tar_with(&[]);
        assert!(archive_content_files(&path, TarFormat::Tar, 0).unwrap_err().to_string().contains("no regular"));
        let (_dir, path) = tar_with(&[("tool", b"x")]);
        assert!(archive_content_files(&path, TarFormat::Tar, 1).is_err());
    }

    #[test]
    fn hidden_zip_hashes_files_and_rejects_unsafe_paths() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("fixture.zip");
        {
            let mut zip = zip::ZipWriter::new(File::create(&path).unwrap());
            zip.start_file("pkg/tool", zip::write::SimpleFileOptions::default()).unwrap();
            zip.write_all(b"tool").unwrap();
            zip.finish().unwrap();
        }
        let files = archive_content_files(&path, TarFormat::Zip, 1).unwrap();
        assert_eq!(files[0].name, "tool");
        assert_eq!(files[0].sha256, hex::encode(Sha256::digest(b"tool")));

        let unsafe_path = dir.path().join("unsafe.zip");
        {
            let mut zip = zip::ZipWriter::new(File::create(&unsafe_path).unwrap());
            zip.start_file("../escape", zip::write::SimpleFileOptions::default()).unwrap();
            zip.write_all(b"bad").unwrap();
            zip.finish().unwrap();
        }
        assert!(archive_content_files(&unsafe_path, TarFormat::Zip, 0).is_err());
    }

    #[test]
    fn hidden_rejects_unsupported_formats_and_strip_counts() {
        let (_dir, path) = tar_with(&[("pkg/tool", b"x")]);
        assert!(archive_content_files(&path, TarFormat::Raw, 0).is_err());
        assert!(archive_content_files(&path, TarFormat::SevenZip, 0).is_err());
        assert!(archive_content_files(&path, TarFormat::Tar, 2).is_err());
    }
}
