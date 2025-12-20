@echo off
title 포트폴리오 관리자
cd /d "C:\python\portfolio"
echo.
echo ========================================
echo   포트폴리오 관리자 시작 중...
echo ========================================
echo.

call venv\Scripts\activate

if errorlevel 1 (
    echo 오류: 가상환경 활성화 실패
    pause
    exit /b 1
)

echo 가상환경 활성화 완료!
echo Streamlit 서버 시작 중...
echo.
echo 브라우저가 자동으로 열립니다.
echo 종료하려면 이 창에서 Ctrl+C를 누르세요.
echo.

streamlit run app.py

pause
