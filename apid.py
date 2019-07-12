import re
import subprocess
import json

from flask import Flask, Response, request
from flask_restful import Resource, Api, abort, reqparse

app = Flask(__name__)
api = Api(app)


class JobsBaseResource(Resource):
    executable = ""

    def query(self, clusterid, procid, constraint, projection, attribute):
        if not self.executable:
            abort(503, message="gotta override this")

        cmd = [self.executable, "-json"]
        if clusterid is not None:
            x = "%d" % clusterid
            if procid is not None:
                x += ".%d" % procid
            cmd.append(x)

        if constraint:
            cmd.extend(["-constraint", constraint])

        if attribute:
            cmd.extend(["-attributes", attribute])
        elif projection:
            cmd.extend(["-attributes", projection + ",clusterid,procid"])

        classads = self._run_cmd(cmd)

        if attribute:
            data = classads[0][attribute]
            return data
        data = []
        for ad in classads:
            job_data = dict()
            job_data["classad"] = {k.lower(): v for k, v in ad.items()}
            job_data["jobid"] = "%s.%s" % (job_data["classad"]["clusterid"], job_data["classad"]["procid"])
            data.append(job_data)
        return data

    def get(self, clusterid=None, procid=None, attribute=None):
        parser = reqparse.RequestParser(trim=True)
        parser.add_argument("projection", default="")
        parser.add_argument("constraint", default="")
        args = parser.parse_args()
        return self.query(clusterid, procid, projection=args.projection, constraint=args.constraint,
                          attribute=attribute)

    def _run_cmd(self, cmd):
        completed = subprocess.run(cmd, capture_output=True, encoding="utf-8")
        if completed.returncode != 0:
            # lazy
            abort(400, message=completed.stderr)

        # super lazy here - the real deal would use the API anyway
        classads = json.loads(completed.stdout)
        if not classads:
            abort(404, message="No job(s) found")

        return classads


class JobsResource(JobsBaseResource):
    executable = "condor_q"


class HistoryResource(JobsBaseResource):
    executable = "condor_history"


class StatusResource(Resource):
    def get(self, name=None):
        parser = reqparse.RequestParser(trim=True)
        parser.add_argument("projection", default="")
        parser.add_argument("constraint", default="")
        args = parser.parse_args()

        cmd = ["condor_status", "-json"]

        if name:
            cmd.append(name)

        if args.constraint:
            cmd.extend(["-constraint", args.constraint])
        if args.projection:
            cmd.extend(["-attributes", args.projection + ",name"])

        completed = subprocess.run(cmd, capture_output=True, encoding="utf-8")
        if completed.returncode != 0:
            # lazy
            if re.search(r"^condor_status: unknown host", completed.stderr, re.MULTILINE):
                abort(404, message=completed.stderr)
            else:
                abort(400, message=completed.stderr)

        # super lazy here - the real deal would use the API anyway
        classads = json.loads(completed.stdout)
        if not classads:
            abort(404, message="No ad(s) found")

        # lowercase all the keys
        classads_lower = [{k.lower(): v for k, v in ad.items()} for ad in classads]

        data = [
            {"name": ad["name"],
             "classad": ad} for ad in classads_lower
        ]

        return data


class ConfigResource(Resource):
    def get(self, attribute=None):
        parser = reqparse.RequestParser(trim=True)
        parser.add_argument("daemon", choices=["master", "schedd", "startd", "collector", "negotiator"])
        args = parser.parse_args()

        cmd = ["condor_config_val", "-raw"]
        if args.daemon:
            cmd.append("-%s" % args.daemon)

        if attribute:
            cmd.append(attribute)
        else:
            cmd.append("-dump")

        completed = subprocess.run(cmd, capture_output=True, encoding="utf-8")
        if completed.returncode != 0:
            # lazy
            if re.search(r"^Not defined:", completed.stderr, re.MULTILINE):
                abort(404, message=completed.stderr)
            else:
                abort(400, message=completed.stderr)

        data = {}
        if attribute:
            data[attribute.lower()] = completed.stdout.rstrip("\n")
        else:
            for line in completed.stdout.split("\n"):
                if line.startswith("#"): continue
                if " = " not in line: continue
                key, value = line.split(" = ", 1)
                data[key.lower()] = value

        return data


api.add_resource(JobsResource, "/v1/jobs", "/v1/jobs/<int:clusterid>",
                 "/v1/jobs/<int:clusterid>/<int:procid>",
                 "/v1/jobs/<int:clusterid>/<int:procid>/<attribute>")
api.add_resource(HistoryResource, "/v1/history", "/v1/history/<int:clusterid>",
                 "/v1/history/<int:clusterid>/<int:procid>",
                 "/v1/history/<int:clusterid>/<int:procid>/<attribute>")
api.add_resource(StatusResource, "/v1/status", "/v1/status/<name>")
api.add_resource(ConfigResource, "/v1/config", "/v1/config/<attribute>")
