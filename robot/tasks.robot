*** Settings ***
Library    LinuxAgent.py

*** Test Cases ***
Apri un Terminale e Lista i File
    Execute Task On UI    Open the terminal, then type 'ls -l' and press enter.
