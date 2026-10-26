from pathlib import Path
exec(Path('D:/UEPro/Test/Scripts/ghs/verify_order_replay_runtime.py').read_text(encoding='utf8').split('steps=run()')[0])
OUT=ROOT/'Saved/OrderReplay/CameraProbe';OUT.mkdir(parents=True,exist_ok=True)
report=dict(success=False,checks=[],captures=[],states={})
def run():
    yield from wait('discover',discover,100)
    yield from wait('initial camera',lambda:not pawn.is_pose_transition_active())
    command('navigate',page='trace');hud.navigate('trace')
    command('replayStart',orderId='TEST-OUT-001',startUtc='2026-10-23T12:00:00.000Z',endUtc='2026-10-23T13:00:00.000Z')
    yield from wait('prepared',lambda:not state()['preparing']);command('replayPause')
    d=json.loads((ROOT/'Content/GHSTwinUI/data/order-replay.json').read_text(encoding='utf8'))
    e=next(e for e in d['events'] if e['kind']=='dropoff' and e['deviceId']=='REPLAY-FORK-03')
    for label,t in [('load',e['time']-1),('pickup',33)]:
        command('replaySeek',time=t);command('replayFollow',id='')
        v=next(v for v in state()['devices'] if v['id']=='REPLAY-FORK-03');p=v['position'];p[2]+=116
        for pitch,dist in [(-62,1100),(-68,1000),(-55,1100),(-65,1400)]:
            pawn.focus_on_target(unreal.Vector(*p),dist,unreal.Rotator(pitch=pitch,yaw=v['yaw']-65),unreal.Vector2D(1920,1080),unreal.Vector2D(720,472),0)
            yield from pause(.3)
            yield from capture(label+str(abs(pitch))+'-'+str(dist))
    command('replayEndRequest');command('replayExitConfirm')
steps=run()
def tick(delta):
    try: next(steps)
    except StopIteration:finish()
    except Exception:finish(traceback.format_exc())
write();handle=unreal.register_slate_post_tick_callback(tick)
