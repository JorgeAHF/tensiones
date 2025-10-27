import time

from app.acquisition.mscl_client import create_demo_client


def test_demo_stream_emits_samples():
    stays = [{"stay_id": "T1", "sensor_id": "ACC-01"}]
    client = create_demo_client(stays, default_fs=128)
    samples = []

    def callback(sample):
        samples.append(sample)
        client.stop_streaming(sample.sensor_id)

    client.start_streaming("ACC-01", callback)
    time.sleep(0.5)
    assert samples
    sample = samples[0]
    assert sample.acceleration_g.shape[1] == 3
