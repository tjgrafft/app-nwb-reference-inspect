# NWB Reference Inspection

Inspect metadata and a small numeric sample from a reference dataset in place.

Runs with Apptainer or Singularity on AWS Batch and non-AWS resources. Provide config.json. The app writes report/report.json and product.json. The resource must have access to private stores. Source data stays remote.

## Publish and run

Create an empty **public** repository with this directory's name under `tjgrafft`, then push the local `main` branch. Its `origin` remote is already set. Give the GitHub repository a description because Brainlife imports it during registration.

```sh
git push -u origin main
```

The included GitHub Actions workflow tests and publishes an amd64 container to GHCR using the repository's built-in `GITHUB_TOKEN`. No personal token or organization authorization is needed. Wait for the workflow to succeed, then make the resulting package **public** in GitHub Packages so the execution resources can pull it. The launcher selects `sha-<current git commit>`, keeping the container aligned with the app source. Every commit used for a run needs a successful container workflow.

After publication, register the app with the prepared `app.json`:

```sh
python3 register_app.py
```

This uses the existing Brainlife CLI session at `~/.config/brainlife.io/.jwt`, or `BRAINLIFE_TOKEN` from the environment. The script does not print credentials and avoids duplicate registrations. The app is scoped to test project `6aa2c76299cc9a38add4d221`.

Both service names have already been enabled, with test project access, on:

- `69bb13cfc34805156f434908` — Taylor Batch Test
- `69c1bedc6d79121812d77c16` — Freesurfer Batch Test
- `62e4a2654a710d5a15a6d50d` — slurm24

Resource registration alone does not prove a job ran. No live inspection jobs have been submitted yet. The test project was empty at setup time; add/register source data before submitting runs. OME-Zarr S3 registration currently requires an S3-backed source project. Do not treat a reference URI as a credential: private S3 stores require resource credentials, and presigned NWB URLs can expire during long queues.

## Inputs and outputs

Provide `config.json` based on `config.json.example`; Brainlife generates it from the app settings. `input` is an HTTPS URL or S3 URI for a reference dataset, or a local path for direct testing. `kind` selects `nwb` or `ome-zarr`. The default sample is 64 numeric elements, with an upper limit of 4,096. `array_path` optionally selects an HDF5 dataset or OME multiscale array.

NWB reads use HTTP range requests. OME-Zarr reads metadata and selected chunks without copying the complete store. Chunk transfer/decompression can exceed the sample size. The app supports Zarr v2 and v3 and does not perform a full scientific analysis or full dataset validation.

The app writes `report/index.html`, `report/html/report.json`, `report/report.json` and a success message in `product.json`. Brainlife archives the `report` directory as `report/html`. Input URLs and credentials are excluded from these reports.

Local container test:

```sh
docker build --platform linux/amd64 -t reference-inspect:local .
docker run --rm --entrypoint python -e PYTHONPATH=/opt/reference-inspect \
  -v "$PWD/tests:/tests:ro" reference-inspect:local -m unittest discover -s /tests -v
```

For private stores, leave `anonymous` false and provision credentials on the resource. For public S3 stores, set `anonymous` true. To use a locally built SIF during debugging, set `REFERENCE_INSPECT_IMAGE` to its path.

[GitHub's container publishing documentation](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images) describes the built-in token workflow.
