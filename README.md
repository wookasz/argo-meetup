# Description

This repository contains the code used during the August 30, 2018 meetup describing how to build a custom reporting feature using `argo`, `helm`, and `codefresh`.

Following the steps below you will:
- Enable `kubernetes` in docker
- Deploy `argo`, `minio`, and `postgres` to your local cluster
- Populate the database with some event data
- Create an `argo` workflow to generate reports based on the data
- Create a `kubernetes` `CronJob` to run the workflow on a schedule
- Deploy the report using `helm`

# Setup

## Enable kubernetes in docker
Enable `kubernetes` in `docker` by navigating to `preferences` then the `kubernetes` tab and enabling it:

![](resources/k8s-docker.png)

Read more: https://docs.docker.com/docker-for-mac/kubernetes/

## Set up helm
If you are not familiar, `helm` is a package manager for `kubernetes`. We'll use it to deploy our services to the cluster.

```bash
$ brew install helm
# the stable repo which helm 3 does not include by default
$ helm repo add stable https://kubernetes-charts.storage.googleapis.com
```

Read more: https://helm.sh/

## Deploy argo
Argo is a `kubernetes` native workflow engine. It is a very powerful tool which allows you to build complex pipelines from simple steps. It will power our custom report generation.

```bash
# install the argo clinet
$ brew install argoproj/tap/argo
# deploy the argo server
$ kubectl create namespace argo
$ kubectl -n argo apply -f https://raw.githubusercontent.com/argoproj/argo/stable/manifests/install.yaml
# to make access to the argo UI easier, change the service type
$ kubectl -n argo patch svc argo-server -p '{"spec": {"type": "LoadBalancer"}}'
```

By default, this will expose the argo-ui at http://localhost:2746. If this conflicts with other locally running services you can edit the service to change its port:

```bash
$ kubectl -n argo edit svc argo-server
# edit spec.ports[0].port
```

Read more: https://github.com/argoproj/argo

## Deploy minio
`minio` is an `AWS S3` compatible object store which you can deploy locally.

```bash
$ helm install stable/minio --name argo-artifacts --set service.type=LoadBalancer
```

Visit the minio UI at http://localhost:9000

Be patient as the service starts up

The default access key and secret key are:
AccessKey: `AKIAIOSFODNN7EXAMPLE`
SecretKey: `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY`

Read more: https://www.minio.io/

### Install minio client
```bash
$ brew install minio/stable/mc
```

You'll need to edit `~/.mc/config.json` adding access and secret from keys above.

```json
{
        "version": "9",
        "hosts": {
                "gcs": {
                        "url": "https://storage.googleapis.com",
                        "accessKey": "YOUR-ACCESS-KEY-HERE",
                        "secretKey": "YOUR-SECRET-KEY-HERE",
                        "api": "S3v2",
                        "lookup": "dns"
                },
                "local": {
                        "url": "http://localhost:9000",
                        "accessKey": "AKIAIOSFODNN7EXAMPLE",
                        "secretKey": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                        "api": "S3v4",
                        "lookup": "auto"
                },
                "play": {
                        "url": "https://play.minio.io:9000",
                        "accessKey": "Q3AM3UQ867SPQQA43P2F",
                        "secretKey": "zuf+tfteSlswRu7BJ86wekitnifILbZam1KYY3TG",
                        "api": "S3v4",
                        "lookup": "auto"
                },
                "s3": {
                        "url": "https://s3.amazonaws.com",
                        "accessKey": "YOUR-ACCESS-KEY-HERE",
                        "secretKey": "YOUR-SECRET-KEY-HERE",
                        "api": "S3v4",
                        "lookup": "dns"
                }
        }
}
```

### Create a bucket for custom reports
```bash
$ mc mb local/custom-reports
```

### [optional] Add minio secrets to argo
This step is not explicitly required to run this tutorial, but you'll want it if you play around with `argo` more.
Modify `workflow-controller-configmap` to add `minio` secrets.

```bash
$ kubectl -n argo edit configmap workflow-controller-configmap
```

add

```yaml
data:
  config: |
    artifactRepository:
      s3:
        bucket: my-bucket
        endpoint: argo-artifacts:9000
        insecure: true
        # accessKeySecret and secretKeySecret are secret selectors.
        # It references the k8s secret named 'argo-artifacts'
        # which was created during the minio helm install. The keys,
        # 'accesskey' and 'secretkey', inside that secret are where the
        # actual minio credentials are stored.
        accessKeySecret:
          name: argo-artifacts
          key: accesskey
        secretKeySecret:
          name: argo-artifacts
          key: secretkey
```

Read more: https://github.com/argoproj/argo/blob/master/docs/getting-started.md#6-reconfigure-the-workflow-controller-to-use-the-minio-artifact-repository


## Deploy postgres
We'll use `postgres` as our database.

```bash
helm repo add bitnami https://charts.bitnami.com/bitnami
helm install postgresql bitnami/postgresql --set global.postgresql.postgresqlPassword=supersecurehaxor  --set service.type=LoadBalancer
```

# Run the workflow
The workflow is `argo`'s unit of work. You can view it in `runner/workflow.yaml`. The workflow here is very simple, it only involves a single "script" step which runs a SQL query, passed as a parameter, and stores the resulting CSV file in `minio`. To learn more about this workflow, or how to write your own, read the documentation at https://github.com/argoproj/argo/tree/master/examples.

## Initialize the db with some data
A provided script will generate some `SQL` to create a new schema, an `events` table, as well as some rows for the table.

The generated events simulate a very simple scenario where the system can send and receive messages in the context of a "session". There are two corresponding events `message_received` and `message_sent`. The report we run will will compute the duration of each session.

```bash
$ python scripts/gen-data.py | psql -d postgres://postgres:supersecurehaxor@db:5432/postgres?sslmode=disable -a
```

## Build the "runner" image
If you so choose you can build your own runner image. You will need to do this if you want to make any changes to the workflow.

Replace `$YOUR_DOCKERHUB_USER` below with your dockerhub username. Sign up at https://hub.docker.com/ if you need one.

```bash
cd runner
export DOKCERHUB_USER=$YOUR_DOCKERHUB_USER
export IMAGE_TAG=dev-$(date +%s)
docker build . -t $DOCKERHUB_USER/meetup-runner:$IMAGE_TAG
docker push $DOCKERHUB_USER/meetup-runner:$IMAGE_TAG
cd ..
```

## Run the workflow
If you followed the instructions up to this point, all that's left is to deploy the `CronJob` to your local k8s cluster.

You can look at the `CronJob` template in `report/templates/cron-job.yaml`. With `helm` the templated variables are replaced with the contents of a values file. In this case, that file is `environments/dev/handl-time.yaml`.

```bash
helm install handle-time report --set image="$DOCKERHUB_USER/meetup_runner" --set image_tag=$IMAGE_TAG -f environments/dev/handle-time.yaml
```

You can also override the cron schedule right on the command line. For example to run on the 12th minute of every hour:

```bash
helm install handle-time report --set image="$DOCKERHUB_USER/meetup_runner" --set image_tag=$IMAGE_TAG -f environments/dev/handle-time.yaml --set schedule="12 * * * *"
```

You can modify the query in `handle-time.yaml` to see how you can generate different reports, changing only that file.

## Verify results
You can view the workflow by navigating your browser to http://localhost:2746, or whatever port you configured `argo-ui` to use.

To see the output of the report navigate to http://http://localhost:9000/minio/custom-reports/meetup/handle-time/. You'll see a timestamped subdirectory for every run of the report. The subdirectory will contain `data.tgz` which is a compressed archive containing your output CSV.
