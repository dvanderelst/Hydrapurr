# 🧱 Build & Release Instructions — HydraPurr Downloader

This project uses **GitHub Actions** to automatically build and package the
Downloader app for **Windows, macOS, and Linux**.

All builds happen in GitHub’s cloud (no need to build locally) and produce
ready-to-run downloadable packages attached to a **GitHub Release**.

---

## 🧩 Logic & Workflow Overview

1. **Build trigger:**  
   Every time you push a Git tag that starts with `v` (e.g. `v1.0.0`),  
   GitHub Actions automatically:
   - Runs the build workflow on Windows, macOS, and Linux runners.
   - Uses PyInstaller to compile `BluetoothDownloader/Downloader.py`.
   - Creates OS-specific launcher scripts so users can double-click to run.
   - Packages the binaries:
     - Windows → `Downloader-Windows.zip`
     - macOS → `Downloader-macOS.zip` (universal binary: Intel + Apple Silicon)
     - Linux → `Downloader-linux.tar.gz`
   - Uploads the packages to a **GitHub Release** titled with the tag (e.g. `v1.0.0`).

2. **Distribution:**  
   The Release page on GitHub contains all three downloadable files.
   Anyone (even without a GitHub account) can download them.

3. **Manual runs:**  
   You can also trigger the workflow manually from GitHub → **Actions → Build Desktop Downloaders → Run workflow**.
   (Manual runs produce artifacts only visible to signed-in users.)

---

## 🚀 Triggering a Build in GitKraken

1. **Open your repo in GitKraken.**
2. **Commit any final changes** you want in the release.

3. **Create a new tag:**
   - In the left panel or graph view, right-click the latest commit →  
     **Tag Commit**  
   - Enter a version tag like `v1.0.0` or `v1.1.2`.

4. **Push the tag to GitHub:**
   - In the top toolbar, click **Push** → ensure “Tags” is checked.  
     (Alternatively, right-click the tag and choose **Push Tag to origin**.)

   > 💡 The tag name (e.g. `v1.0.0`) becomes the Release version number.

5. **Wait a few minutes.**
   - GitHub Actions will start automatically.
   - You can monitor progress under the **Actions** tab on GitHub.

6. **Get your release:**
   - When the workflow finishes, go to **Releases** on your repo.
   - Open the release titled `v1.0.0`.
   - Download the OS-specific files:
     - `Downloader-Windows.zip`
     - `Downloader-macOS.zip`
     - `Downloader-linux.tar.gz`

7. **Share the download link** directly from the Release page.

---

## 🛠 Updating for a New Version
When you’re ready to publish another version:
1. Make your changes.
2. Commit them.
3. Create and push a new tag (e.g. `v1.1.0`).
4. The workflow builds and publishes a new release automatically.

---

## 🧠 Notes
- You can also run builds manually without tagging, but only you (and other repo members) can download those artifacts.
- The macOS build is a **universal binary** that runs on both Intel and Apple Silicon Macs.
- If you ever want to sign your executables or add auto-updaters, those can be added later.

---

**In summary:**  
> **Tag → Push → GitHub builds → Release appears → Everyone can download.**
