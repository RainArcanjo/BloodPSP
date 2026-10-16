import sys

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        from bloodpsp_launcher.smoke import main
        raise SystemExit(main(sys.argv[2]))
    else:
        from bloodpsp_launcher.app import main
        raise SystemExit(main())
