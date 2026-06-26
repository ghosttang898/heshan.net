#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/backend"
mvn spring-boot:run
