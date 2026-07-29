#!/usr/bin/env bash
# AGORA PM 병렬 실행기 — stdin 으로 받은 스크립트를 dgx-02~11 에서 동시에 실행한다.
#   사용법:  echo 'hostname' | ./dgx-fan.sh            # 전체
#            echo 'hostname' | ./dgx-fan.sh dgx-02 dgx-07
set -uo pipefail

NODES=("$@")
if [ ${#NODES[@]} -eq 0 ]; then
  NODES=(dgx-02 dgx-03 dgx-04 dgx-05 dgx-06 dgx-07 dgx-08 dgx-09 dgx-10 dgx-11)
fi

SCRIPT=$(cat)
OUT=$(mktemp -d)

for n in "${NODES[@]}"; do
  ( printf '%s' "$SCRIPT" | ssh -o BatchMode=yes -o ConnectTimeout=15 "$n" 'bash -s' \
      >"$OUT/$n.log" 2>&1; echo $? >"$OUT/$n.rc" ) &
done
wait

fail=0
for n in "${NODES[@]}"; do
  rc=$(cat "$OUT/$n.rc" 2>/dev/null || echo 99)
  [ "$rc" = "0" ] || fail=1
  echo "########## $n (rc=$rc) ##########"
  cat "$OUT/$n.log"
done
rm -rf "$OUT"
exit $fail
