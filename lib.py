import asyncio
import functools
import traceback
import os

import docker
from database import Database
from messages import SubmitMessage

doc = docker.from_env()
async def build_image(msg, solution):
    print(f"Building for {msg.author.name}")
    status = await msg.reply("Building...")
    with open("runner/src/code.rs", "wb+") as f:
        f.write(solution)

    loop = asyncio.get_event_loop()

    try:
        await loop.run_in_executor(None, functools.partial(doc.images.build, path="runner", tag=f"ferris-elf-{msg.author.id}"))
        return True
    except docker.errors.BuildError as err:
        print(f"Build error: {err}")
        e = ""
        for chunk in err.build_log:
            e += chunk.get("stream") or ""
        await msg.reply(f"Error building benchmark: {err}", file=discord.File(io.BytesIO(e.encode("utf-8")), "build_log.txt"))
        return False
    finally:
        await status.delete()

async def run_image(msg, input):
    print(f"Running for {msg.author.name}")
    # input = ','.join([str(int(x)) for x in input])
    status = await msg.reply("Running benchmark...")
    loop = asyncio.get_event_loop()
    try:
        out = await loop.run_in_executor(None, functools.partial(doc.containers.run, f"ferris-elf-{msg.author.id}", f"timeout 60 ./target/release/ferris-elf", environment=dict(INPUT=input), remove=True, stdout=True, mem_limit="24g", network_mode="none"))
        out = out.decode("utf-8")
        print(out)
        return out
    except docker.errors.ContainerError as err:
        print(f"Run error: {err}")
        await msg.reply(f"Error running benchmark: {err}", file=discord.File(io.BytesIO(err.stderr), "stderr.txt"))
    finally:
        await status.delete()

async def benchmark(submit_msg: SubmitMessage):
    (msg,day,code,part) = submit_msg.msg,submit_msg.day,submit_msg.code,submit_msg.part
    build = await build_image(msg, code)
    if not build:
        return
    
    day_path = f"{day}/"
    try:
        onlyfiles = [f for f in os.listdir(day_path) if os.isfile(os.path.join(day_path, f))]
    except:
        await msg.reply(f"Failed to read input files for day {day}, part {part}")
        return

    db = Database().get()

    verified = False
    results = []
    for (i, file) in enumerate(onlyfiles):
        rows = db.cursor().execute("SELECT answer2 FROM solutions WHERE key = ? AND day = ? AND part = ?", (file, day, part))

        with open(os.path.join(day_path, file), "r") as f:
            input = f.read()

        status = await msg.reply(f"Benchmarking input {i+1}")
        out = await run_image(msg, input)
        if not out:
            return
        await status.delete()

        result = {}
        #TODO: get the answer and the bench results from the docker and verify them here

        cur.execute("INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?)", (str(msg.author.id), code, day, part, result["median"], result["answer"], result["answer"]))
        results.append(result)
    

    median = avg([r["median"] for r in results])
    average = avg([r["average"] for r in results])

    if verified:
        await msg.reply(embed=discord.Embed(title="Benchmark complete", description=f"Median: **{ns(median)}**\nAverage: **{ns(average)}**"))
    else:
        await msg.reply(embed=discord.Embed(title="Benchmark complete (Unverified)", description=f"Median: **{ns(median)}**\nAverage: **{ns(average)}**"))

    db.commit()
    print("Inserted results into DB")
