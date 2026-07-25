from folderscribe.main import main


def test_main_returns_zero() -> None:
    assert main() == 0


def test_main_prints_message(capsys) -> None:
    main()
    captured = capsys.readouterr()
    assert captured.out.strip() == "FolderScribe is ready."
