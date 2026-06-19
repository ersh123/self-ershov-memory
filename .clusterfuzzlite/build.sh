#!/bin/bash -eu

export PYTHONPATH="$SRC/hermes-ershov/src${PYTHONPATH:+:$PYTHONPATH}"

for fuzzer in $(find "$SRC/hermes-ershov/fuzzers" -name '*_fuzzer.py'); do
  fuzzer_basename=$(basename -s .py "$fuzzer")
  fuzzer_package="${fuzzer_basename}.pkg"

  pyinstaller --distpath "$OUT" --onefile --name "$fuzzer_package" "$fuzzer"

  cat > "$OUT/$fuzzer_basename" <<EOF
#!/bin/sh
# LLVMFuzzerTestOneInput for ClusterFuzzLite fuzzer detection.
this_dir=\$(dirname "\$0")
"\$this_dir/$fuzzer_package" "\$@"
EOF
  chmod +x "$OUT/$fuzzer_basename"
done
