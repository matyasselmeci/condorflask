import subprocess
import json

from flask import (Flask, Response, request)
app = Flask(__name__)


def json_response(data, status=200):
    return Response(json.dumps(data), mimetype="application/json",
                    status=status)


def error_response(message, status=400):
    data = {"error": message}
    return json_response(data, status)


def jobs_or_history(prog, clusterid, procid, constraint, projection):
    cmd = [prog]
    try:
        if procid is not None:
            if clusterid is None:
               return error_response("clusterid not specified")
            cmd.append("%d.%d" % (clusterid, procid))
        elif clusterid is not None:
            cmd.append("%d" % clusterid)
    except (ValueError, TypeError) as e:
        # lazy
        return error_response("Invalid value for clusterid or procid: %s" % e)

    if constraint:
        cmd.append("-constraint")
        cmd.append(constraint)

    split_projection = []
    if projection:
        split_projection = projection.split(",")
        cmd.extend(["-af:jt"] + split_projection)
    else:
        cmd.append("-json")

    completed = subprocess.run(cmd, capture_output=True, encoding="utf-8")
    if completed.returncode != 0:
        return error_response(completed.stderr)

    # super lazy here - the real deal would use the API anyway
    if not projection:
        classads = json.loads(completed.stdout)
        if not classads:
            return error_response("No jobs found", 404)
        data = []
        for ad in classads:
            job_data = {k.lower(): v for k, v in ad.items()}
            job_data["jobid"] = "%s.%s" % (job_data["clusterid"], job_data["procid"])
            data.append(job_data)
        return json_response(data)
    else:
        data = []
        for line in completed.stdout.split("\n"):
            if not line: continue
            keys = ["jobid"] + split_projection
            values = line.split("\t")
            job_data = dict(zip(keys, values))
            data.append(job_data)
        return json_response(data)


@app.route("/v1/jobs")
@app.route("/v1/jobs/<int:clusterid>")
@app.route("/v1/jobs/<int:clusterid>/<int:procid>")
def jobs(clusterid=None, procid=None):
    constraint = request.args.get("constraint", "")
    projection = request.args.get("projection", "owner,cmd,args").lower()
    return jobs_or_history("condor_q", clusterid=clusterid, procid=procid, constraint=constraint, projection=projection)


@app.route("/v1/history")
@app.route("/v1/history/<int:clusterid>")
@app.route("/v1/history/<int:clusterid>/<int:procid>")
def history(clusterid=None, procid=None):
    constraint = request.args.get("constraint", "")
    projection = request.args.get("projection", "owner,cmd,args").lower()
    return jobs_or_history("condor_history", clusterid=clusterid, procid=procid, constraint=constraint, projection=projection)
