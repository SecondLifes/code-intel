@echo off
setlocal enabledelayedexpansion

:: resize-images.bat
:: Downscales PNG banner images (e.g. docs\images\*.png) using ImageMagick.
:: Shrink-only — never upscales a smaller image — and strips metadata to
:: cut file size further. Meant for the AI-generated README banner images
:: this workspace's docs\image-prompts.md produces, which commonly come
:: back from image models at multi-megabyte, far-larger-than-needed
:: resolutions.
::
:: Usage:
::   tools\resize-images.bat                      (defaults to docs\images next to this script's parent folder)
::   tools\resize-images.bat "C:\path\to\images"   (explicit folder)
::   tools\resize-images.bat "C:\path\to\images" 1600x800   (explicit max size, default is 1280x640)

set "SCRIPT_DIR=%~dp0"
set "TARGET_DIR=%~1"
set "MAX_SIZE=%~2"

if "%TARGET_DIR%"=="" set "TARGET_DIR=%SCRIPT_DIR%..\docs\images"
if "%MAX_SIZE%"=="" set "MAX_SIZE=1280x640"

where magick >nul 2>&1
if errorlevel 1 (
  echo ERROR: ImageMagick's "magick" command was not found on PATH.
  echo Install it from https://imagemagick.org/script/download.php and re-run.
  exit /b 1
)

if not exist "%TARGET_DIR%" (
  echo ERROR: Folder not found: "%TARGET_DIR%"
  exit /b 1
)

echo Resizing PNG images in "%TARGET_DIR%" to fit within %MAX_SIZE% (shrink-only), stripping metadata...
echo.

set "COUNT=0"
set "FAILED=0"
for %%F in ("%TARGET_DIR%\*.png") do (
  echo   - %%~nxF
  magick "%%F" -resize "%MAX_SIZE%>" -strip -quality 85 "%%F"
  if errorlevel 1 (
    echo     FAILED: %%~nxF
    set /a FAILED+=1
  ) else (
    set /a COUNT+=1
  )
)

echo.
if %COUNT% equ 0 (
  if %FAILED% equ 0 (
    echo No PNG files found in "%TARGET_DIR%".
  )
) else (
  echo Done — resized %COUNT% image^(s^).
)
if %FAILED% gtr 0 (
  echo %FAILED% image^(s^) failed — see above.
  exit /b 1
)

endlocal
