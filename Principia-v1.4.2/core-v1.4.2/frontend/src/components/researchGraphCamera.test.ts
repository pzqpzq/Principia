import { describe, expect, it } from 'vitest';
import { fittedGraphCamera, savedGraphCamera } from './researchGraphCamera';

describe('research map framing', () => {
  it('fits uninitialized projects but restores real gestures at the origin', () => {
    expect(savedGraphCamera({})).toBeUndefined();
    expect(savedGraphCamera({x:0,y:0,ratio:1})).toBeUndefined();
    expect(savedGraphCamera({x:0,y:0,angle:0,ratio:1})).toEqual({x:0,y:0,angle:0,ratio:1});
    expect(savedGraphCamera({x:.3,y:.7,angle:.2,ratio:1.6})).toEqual({x:.3,y:.7,angle:.2,ratio:1.6});
    expect(savedGraphCamera({x:'bad',y:.5,ratio:1})).toBeUndefined();
  });
  it('centers the actual visible extent and leaves room at narrow canvas edges', () => {
    const camera=fittedGraphCamera([{x:.2,y:.1,screenX:20,screenY:50},{x:.8,y:.7,screenX:380,screenY:650}],400,700)!;
    expect(camera.x).toBe(.5); expect(camera.y).toBeCloseTo(.4);
    expect(360/camera.ratio).toBeLessThanOrEqual(220);
    expect(600/camera.ratio).toBeLessThanOrEqual(520);
    expect(fittedGraphCamera([],400,700)).toBeUndefined();
    expect(fittedGraphCamera([{x:.4,y:.3,screenX:50,screenY:50}],0,700)).toBeUndefined();
  });
});
